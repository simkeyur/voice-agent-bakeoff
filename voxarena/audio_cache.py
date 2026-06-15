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


def _cache_path(text: str) -> str:
    """Stable hash-keyed path for a given utterance text."""
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]
    cache_dir = os.path.join(settings.AUDIO_DIR, CACHE_SUBDIR)
    return os.path.join(cache_dir, f"{digest}.wav")


def _pick_engine() -> Optional[str]:
    """Choose the best available TTS engine: OpenAI > Google > macOS ``say``."""
    if get_setting("OPENAI_API_KEY"):
        return "openai"
    if get_setting("GOOGLE_API_KEY"):
        return "google"
    if sys.platform == "darwin":
        return "mac"
    return None


def _synthesize(text: str, output_path: str, engine: str) -> None:
    from voxarena.generate_audio import (
        generate_tts_google,
        generate_tts_mac,
        generate_tts_openai,
    )
    if engine == "openai":
        generate_tts_openai(text, output_path, get_setting("OPENAI_API_KEY"))
    elif engine == "google":
        generate_tts_google(text, output_path, get_setting("GOOGLE_API_KEY"))
    elif engine == "mac":
        generate_tts_mac(text, output_path)
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
    currently-known utterance text. Returns the number of files removed.

    Called on bootstrap so the synth cache doesn't grow without bound as
    templates / utterances evolve.
    """
    cache_dir = os.path.join(settings.AUDIO_DIR, CACHE_SUBDIR)
    if not os.path.isdir(cache_dir):
        return 0

    keep = {os.path.basename(_cache_path(t)) for t in keep_texts if t and t.strip()}
    keep.add(os.path.basename(_cache_path("__silent__")))

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

    Cache layout: ``AUDIO_DIR/synth/{sha256(text)[:16]}.wav``. Idempotent and
    safe to call repeatedly — only synthesizes when the file is missing.
    """
    if not text or not text.strip():
        path = _cache_path("__silent__")
        if not os.path.exists(path):
            _write_silent_wav(path)
        return path

    path = _cache_path(text)
    if os.path.exists(path):
        return path

    engine = _pick_engine()
    if not engine:
        logger.warning(
            "No TTS engine available (set OPENAI_API_KEY / GOOGLE_API_KEY, "
            f"or run on macOS). Falling back to silent WAV for: '{text[:60]}'"
        )
        _write_silent_wav(path)
        return path

    try:
        _synthesize(text, path, engine)
    except Exception as e:
        logger.error(f"TTS synthesis failed for '{text[:60]}' via {engine}: {e}. Using silent fallback.")
        _write_silent_wav(path)

    return path
