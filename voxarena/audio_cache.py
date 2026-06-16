"""Hash-keyed audio cache with on-demand TTS synthesis.

Solves the stale-audio bug where ``{utterance_id}.wav`` could fall out of
sync with the text it was supposed to render — when a template's utterance
text changed, the old WAV still got injected and the model heard the wrong
prompt.

Each cache entry is keyed by ``sha256(text)``, so any text change
automatically invalidates the cache and a fresh WAV is synthesized on the
next run. Synthesized files live under ``AUDIO_DIR/synth/`` so they don't
collide with any manually-recorded files a user might have dropped in
``AUDIO_DIR``.
"""
from __future__ import annotations

import hashlib
import os
import sys
import wave
from typing import Optional

from loguru import logger

from voxarena.config import get_setting, settings


CACHE_SUBDIR = "synth"

# Cache the digest of the engine + model knobs in the WAV's filename so changes
# to the engine/voice automatically invalidate stale recordings. We don't bake
# the API key in (it's a secret, and two keys for the same model produce the
# same audio).
#
# Local-first by default — no API call, no rate limits, no network round-trip,
# and the resulting audio is good enough for the harness's purpose
# (deterministic user-turn injection). API engines are tried next when the
# local OS doesn't ship a synth (or the user explicitly opts in).
ENGINE_FALLBACK_CHAIN = ("local", "openai", "google")


def _local_engine_available() -> bool:
    """Is the platform's built-in TTS reachable right now?"""
    import shutil as _shutil
    if sys.platform == "darwin":
        return _shutil.which("say") is not None
    if sys.platform.startswith("linux"):
        return _shutil.which("espeak-ng") is not None or _shutil.which("espeak") is not None
    if sys.platform == "win32":
        return _shutil.which("powershell") is not None
    return False


def _engine_available(engine: str) -> bool:
    if engine == "openai":
        return bool(get_setting("OPENAI_API_KEY"))
    if engine == "google":
        return bool(get_setting("GOOGLE_API_KEY"))
    if engine == "local":
        return _local_engine_available()
    return False


def _engine_signature(engine: str) -> str:
    """Per-engine signature used in the cache key so swapping voice/model
    re-synthesizes instead of returning stale audio."""
    if engine == "openai":
        model = get_setting("OPENAI_TTS_MODEL") or settings.OPENAI_TTS_MODEL
        voice = get_setting("OPENAI_TTS_VOICE") or settings.OPENAI_TTS_VOICE
        return f"openai:{model}:{voice}"
    if engine == "google":
        voice = get_setting("GOOGLE_TTS_VOICE") or settings.GOOGLE_TTS_VOICE
        return f"google:{voice}"
    if engine == "local":
        return f"local:{sys.platform}"
    return engine


def _resolved_engine_chain() -> list[str]:
    """Build the actual engine try-order: preferred first, then fallbacks.
    Honours the TTS_ENGINE setting; `auto` defers to ENGINE_FALLBACK_CHAIN."""
    preferred = (get_setting("TTS_ENGINE") or settings.TTS_ENGINE or "auto").lower()
    chain = list(ENGINE_FALLBACK_CHAIN)
    if preferred != "auto" and preferred in chain:
        chain.remove(preferred)
        chain.insert(0, preferred)
    elif preferred != "auto":
        logger.warning(f"Unknown TTS_ENGINE='{preferred}', falling back to auto.")
    # Drop unavailable engines from the chain so we don't waste a retry loop on them.
    return [e for e in chain if _engine_available(e)]


def _cache_path(text: str, signature: str = "") -> str:
    """Stable hash-keyed path for a given utterance text. The signature lets
    different engine/voice combinations coexist in the cache without collision."""
    digest_input = f"{signature}|{text.strip().lower()}".encode("utf-8")
    digest = hashlib.sha256(digest_input).hexdigest()[:16]
    cache_dir = os.path.join(settings.AUDIO_DIR, CACHE_SUBDIR)
    return os.path.join(cache_dir, f"{digest}.wav")


def _synthesize(text: str, output_path: str, engine: str) -> None:
    from voxarena.generate_audio import (
        generate_tts_google,
        generate_tts_local,
        generate_tts_openai,
    )
    if engine == "openai":
        generate_tts_openai(text, output_path, get_setting("OPENAI_API_KEY"))
    elif engine == "google":
        generate_tts_google(text, output_path, get_setting("GOOGLE_API_KEY"))
    elif engine == "local":
        generate_tts_local(text, output_path)
    else:
        raise RuntimeError(f"Unknown TTS engine: {engine}")


def _write_silent_wav(path: str, duration_sec: float = 1.5) -> None:
    """Last-resort fallback when no TTS engine is available — keeps the
    pipeline alive but produces no speech."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sample_rate = 16000
    silent_data = b"\x00\x00" * int(sample_rate * duration_sec)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(silent_data)


def prune_orphan_synth_files(keep_texts: list[str]) -> int:
    """Delete synthesized WAV files in AUDIO_DIR/synth/ that don't match any
    currently-known utterance text under any plausible engine signature.

    Called on bootstrap so the synth cache doesn't grow without bound as
    templates / utterances / TTS settings evolve. We compute the cache name
    for every (text, engine-signature) combo we currently know about, plus
    the legacy unsigned name (so cache files from older versions survive a
    rollback gracefully — they're orphans on the *next* prune pass only
    after their utterances are removed).
    """
    cache_dir = os.path.join(settings.AUDIO_DIR, CACHE_SUBDIR)
    if not os.path.isdir(cache_dir):
        return 0

    signatures = [_engine_signature(e) for e in ENGINE_FALLBACK_CHAIN] + [""]
    keep: set[str] = set()
    for text in keep_texts:
        if not text or not text.strip():
            continue
        for sig in signatures:
            keep.add(os.path.basename(_cache_path(text, sig)))
    for sig in signatures:
        keep.add(os.path.basename(_cache_path("__silent__", sig)))

    removed = 0
    for name in os.listdir(cache_dir):
        if not name.endswith(".wav"):
            continue
        if name not in keep:
            try:
                os.remove(os.path.join(cache_dir, name))
                removed += 1
            except OSError as e:
                logger.warning(f"Failed to prune orphan synth file {name}: {e}")
    if removed:
        logger.info(f"Pruned {removed} orphan synth WAV file(s) from {cache_dir}.")
    return removed


def resolve_audio(text: str) -> str:
    """Return a path to a WAV file matching ``text``, synthesizing it if needed.

    Honours the ``TTS_ENGINE`` setting: tries the preferred engine first, then
    falls through ``ENGINE_FALLBACK_CHAIN`` if it isn't configured or
    synthesis fails. Cache entries are signed by engine+voice so switching
    engines produces a fresh WAV instead of returning stale audio.
    """
    if not text or not text.strip():
        path = _cache_path("__silent__")
        if not os.path.exists(path):
            _write_silent_wav(path)
        return path

    chain = _resolved_engine_chain()
    if not chain:
        path = _cache_path(text)
        logger.warning(
            "No TTS engine available. Set OPENAI_API_KEY / GOOGLE_API_KEY, "
            "install espeak-ng (Linux), or run on macOS / Windows for local TTS. "
            f"Falling back to silent WAV for: '{text[:60]}'"
        )
        _write_silent_wav(path)
        return path

    last_error: Optional[Exception] = None
    for engine in chain:
        signature = _engine_signature(engine)
        path = _cache_path(text, signature)
        if os.path.exists(path):
            return path
        try:
            _synthesize(text, path, engine)
            return path
        except Exception as e:
            last_error = e
            logger.warning(
                f"TTS synthesis failed via {engine} for '{text[:60]}': {e}. "
                f"Trying next engine in fallback chain."
            )

    # Every engine in the chain failed — silent fallback so the run doesn't stall.
    path = _cache_path(text)
    logger.error(
        f"All TTS engines failed for '{text[:60]}' (last error: {last_error}). "
        "Using silent fallback."
    )
    _write_silent_wav(path)
    return path
