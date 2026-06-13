import os
import yaml
from loguru import logger
from src.config import settings

def generate_tts_openai(text: str, output_path: str, api_key: str):
    """Generate TTS audio using OpenAI's API."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    
    logger.info(f"Generating OpenAI TTS for: '{text}'")
    # Requesting output in WAV format
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",  # using a warm customer-like voice
        input=text,
        response_format="wav"
    )
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)
    logger.success(f"Saved audio to {output_path}")

def generate_tts_google(text: str, output_path: str, api_key: str):
    """Generate TTS audio using Google's Text-to-Speech API."""
    from google.cloud import texttospeech
    
    logger.info(f"Generating Google TTS for: '{text}'")
    # Google client reads GOOGLE_API_KEY from environment automatically or we can configure it
    # We set environment variable for the Google SDK if not already set
    if "GOOGLE_API_KEY" not in os.environ and api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        
    client = texttospeech.TextToSpeechClient()
    
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Journey-F"  # High quality natural voice
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,  # 16-bit PCM WAV
        sample_rate_hertz=16000
    )
    
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
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
    try:
        cmd = [
            "say",
            "--file-format=WAVE",
            "--data-format=LEI16@16000",
            "-o", output_path,
            text
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.success(f"Saved audio to {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"macOS say failed: {e.stderr.decode().strip() if e.stderr else str(e)}")
        raise

def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate TTS audio files for the voice agent bake-off.")
    parser.add_argument("--use-mac-tts", action="store_true", help="Force use of macOS built-in 'say' command.")
    args, _ = parser.parse_known_args()
    
    utterances_path = os.path.join(settings.SCRIPT_DIR, "utterances.yaml")
    if not os.path.exists(utterances_path):
        logger.error(f"Utterances file not found at {utterances_path}")
        return
        
    with open(utterances_path, "r") as f:
        utterances = yaml.safe_load(f)
        
    logger.info(f"Found {len(utterances)} utterances to generate.")
    
    # Check for active API credentials
    openai_key = settings.OPENAI_API_KEY
    google_key = settings.GOOGLE_API_KEY
    
    is_mac = sys.platform == "darwin"
    
    # Decide which TTS engine to use
    if args.use_mac_tts:
        if not is_mac:
            logger.error("macOS TTS was requested but this system is not running macOS.")
            return
        logger.info("Using macOS built-in 'say' command for TTS.")
        tts_mode = "mac"
    elif not openai_key and not google_key:
        if is_mac:
            logger.info("No API keys found. Defaulting to macOS built-in 'say' command for local TTS.")
            tts_mode = "mac"
        else:
            logger.error("No API keys found in settings and not on macOS. Please define OPENAI_API_KEY or GOOGLE_API_KEY in .env.")
            return
    else:
        # Fall back to OpenAI or Google if keys are set
        if openai_key:
            logger.info("Using OpenAI TTS API.")
            tts_mode = "openai"
        else:
            logger.info("Using Google TTS API.")
            tts_mode = "google"
            
    for i, utt in enumerate(utterances):
        utt_id = utt["id"]
        text = utt["text"]
        output_path = os.path.join(settings.AUDIO_DIR, f"{utt_id}.wav")
        
        # Avoid re-generating if file already exists
        if os.path.exists(output_path):
            logger.info(f"[{i+1}/{len(utterances)}] Audio already exists for {utt_id}, skipping.")
            continue
            
        try:
            if tts_mode == "mac":
                generate_tts_mac(text, output_path)
            elif tts_mode == "openai":
                generate_tts_openai(text, output_path, openai_key)
            elif tts_mode == "google":
                generate_tts_google(text, output_path, google_key)
        except Exception as e:
            logger.error(f"Failed to generate TTS for {utt_id}: {e}")
            
    logger.success("TTS Generation complete.")

if __name__ == "__main__":
    main()
