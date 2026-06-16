import os
import shutil
import sys
import yaml
from loguru import logger
from voxarena.config import get_setting, settings


def generate_tts_openai(text: str, output_path: str, api_key: str, model: str = None, voice: str = None):
    """Generate TTS audio using OpenAI's API.

    `model` defaults to `OPENAI_TTS_MODEL` setting (e.g. "tts-1", "tts-1-hd").
    `voice` defaults to `OPENAI_TTS_VOICE` setting (e.g. "nova", "alloy", "shimmer").
    """
    from openai import OpenAI

    model = model or get_setting("OPENAI_TTS_MODEL") or settings.OPENAI_TTS_MODEL
    voice = voice or get_setting("OPENAI_TTS_VOICE") or settings.OPENAI_TTS_VOICE

    client = OpenAI(api_key=api_key)
    logger.info(f"Generating OpenAI TTS ({model}/{voice}) for: '{text}'")
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        response_format="wav",
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)
    logger.success(f"Saved audio to {output_path}")


def generate_tts_google(text: str, output_path: str, api_key: str, voice: str = None):
    """Generate TTS audio using Google's Text-to-Speech API.

    `voice` defaults to `GOOGLE_TTS_VOICE` setting (e.g. "en-US-Journey-F").
    """
    from google.cloud import texttospeech

    voice = voice or get_setting("GOOGLE_TTS_VOICE") or settings.GOOGLE_TTS_VOICE
    logger.info(f"Generating Google TTS ({voice}) for: '{text}'")

    if "GOOGLE_API_KEY" not in os.environ and api_key:
        os.environ["GOOGLE_API_KEY"] = api_key

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice_params = texttospeech.VoiceSelectionParams(language_code="en-US", name=voice)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
    )

    response = client.synthesize_speech(
        input=synthesis_input, voice=voice_params, audio_config=audio_config
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as out:
        out.write(response.audio_content)
    logger.success(f"Saved audio to {output_path}")


def generate_tts_mac(text: str, output_path: str):
    """Generate TTS audio using macOS built-in `say` command."""
    import subprocess
    logger.info(f"Generating macOS local TTS for: '{text}'")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        "say",
        "--file-format=WAVE",
        "--data-format=LEI16@16000",
        "-o", output_path,
        text,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.success(f"Saved audio to {output_path}")


def generate_tts_linux(text: str, output_path: str):
    """Generate TTS audio on Linux using `espeak-ng` (preferred) or `espeak`.

    Install with: `apt install espeak-ng` / `brew install espeak`. Raises
    RuntimeError if neither is available, so the caller can fall back.
    """
    import subprocess

    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary:
        raise RuntimeError(
            "Linux local TTS requires `espeak-ng` (or `espeak`) on PATH. "
            "Install with `apt install espeak-ng`."
        )

    logger.info(f"Generating Linux local TTS via {os.path.basename(binary)} for: '{text}'")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # `-w` writes a 22.05kHz mono 16-bit WAV; widely compatible.
    subprocess.run([binary, "-w", output_path, text], check=True, capture_output=True)
    logger.success(f"Saved audio to {output_path}")


def generate_tts_windows(text: str, output_path: str):
    """Generate TTS audio on Windows using PowerShell's `System.Speech.Synthesis`."""
    import subprocess

    logger.info(f"Generating Windows local TTS (System.Speech) for: '{text}'")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # PowerShell one-liner: load System.Speech, write the WAV to disk.
    escaped_text = text.replace("'", "''")
    escaped_path = output_path.replace("'", "''")
    ps_script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{escaped_path}'); "
        f"$s.Speak('{escaped_text}'); "
        "$s.Dispose()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        check=True, capture_output=True,
    )
    logger.success(f"Saved audio to {output_path}")


def generate_tts_local(text: str, output_path: str):
    """Generate TTS audio using the platform's built-in synth (no API keys)."""
    if sys.platform == "darwin":
        return generate_tts_mac(text, output_path)
    if sys.platform.startswith("linux"):
        return generate_tts_linux(text, output_path)
    if sys.platform == "win32":
        return generate_tts_windows(text, output_path)
    raise RuntimeError(f"No local TTS available for platform: {sys.platform}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate TTS audio files for VoxArena scripted runs.")
    parser.add_argument("--engine", choices=["auto", "openai", "google", "local"], default="auto",
                        help="Override the TTS engine (default: TTS_ENGINE setting, falling back through the chain).")
    args, _ = parser.parse_known_args()

    utterances_path = os.path.join(settings.SCRIPT_DIR, "utterances.yaml")
    if not os.path.exists(utterances_path):
        logger.error(f"Utterances file not found at {utterances_path}")
        return

    with open(utterances_path, "r") as f:
        utterances = yaml.safe_load(f)
    logger.info(f"Found {len(utterances)} utterances to generate.")

    from voxarena.audio_cache import resolve_audio
    for i, utt in enumerate(utterances):
        utt_id = utt["id"]
        text = utt["text"]
        path = resolve_audio(text)
        logger.info(f"[{i+1}/{len(utterances)}] {utt_id}: {path}")
    logger.success("TTS Generation complete.")


if __name__ == "__main__":
    main()
