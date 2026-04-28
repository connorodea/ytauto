"""Text-to-speech service using Deepgram Aura, OpenAI TTS, or ElevenLabs."""

from __future__ import annotations

from pathlib import Path

import httpx
import openai

from ytauto.config.settings import Settings
from ytauto.services.retry import retry

OPENAI_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")

# Deepgram Aura voice models
DEEPGRAM_VOICES = {
    # Male voices
    "aura-orion-en": "Orion (male, deep & authoritative)",
    "aura-arcas-en": "Arcas (male, warm & engaging)",
    "aura-perseus-en": "Perseus (male, confident & clear)",
    "aura-angus-en": "Angus (male, friendly & approachable)",
    "aura-orpheus-en": "Orpheus (male, rich & dramatic)",
    "aura-helios-en": "Helios (male, energetic & bright)",
    "aura-zeus-en": "Zeus (male, powerful & commanding)",
    # Female voices
    "aura-asteria-en": "Asteria (female, warm & natural)",
    "aura-luna-en": "Luna (female, soft & soothing)",
    "aura-stella-en": "Stella (female, bright & clear)",
    "aura-athena-en": "Athena (female, professional)",
    "aura-hera-en": "Hera (female, authoritative)",
}

DEEPGRAM_API_URL = "https://api.deepgram.com/v1/speak"


def synthesize_voiceover(
    text: str,
    output_path: Path,
    voice: str = "aura-orion-en",
    settings: Settings | None = None,
) -> Path:
    """Generate speech audio from text.

    Provider priority: deepgram > openai > elevenlabs (based on settings).
    Returns the path to the generated audio file.
    """
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    provider = settings.default_tts_provider

    if provider == "deepgram" and settings.has_deepgram():
        return _deepgram_tts(text, output_path, voice, settings)
    elif provider == "elevenlabs" and settings.has_elevenlabs():
        return _elevenlabs_tts(text, output_path, voice, settings)
    elif provider == "openai" and settings.has_openai():
        return _openai_tts(text, output_path, voice, settings)
    # Fallback chain
    elif settings.has_deepgram():
        return _deepgram_tts(text, output_path, voice, settings)
    elif settings.has_openai():
        return _openai_tts(text, output_path, voice, settings)
    elif settings.has_elevenlabs():
        return _elevenlabs_tts(text, output_path, voice, settings)
    else:
        raise RuntimeError("No TTS API key configured. Run 'ytauto setup'.")


def _deepgram_tts(text: str, output_path: Path, voice: str, settings: Settings) -> Path:
    """Generate speech using Deepgram Aura TTS API."""
    # Default to orion if voice isn't a Deepgram model
    if voice not in DEEPGRAM_VOICES:
        voice = "aura-orion-en"

    api_key = settings.deepgram_api_key.get_secret_value()

    # Deepgram has a ~2000 char limit per request — chunk longer texts
    chunks = _chunk_text(text, max_chars=1900)

    if len(chunks) == 1:
        _deepgram_request(chunks[0], voice, api_key, output_path)
    else:
        chunk_paths: list[Path] = []
        for i, chunk in enumerate(chunks):
            chunk_path = output_path.parent / f"_dg_chunk_{i:03d}.mp3"
            _deepgram_request(chunk, voice, api_key, chunk_path)
            chunk_paths.append(chunk_path)

        _concat_audio(chunk_paths, output_path)

        for cp in chunk_paths:
            cp.unlink(missing_ok=True)

    return output_path


@retry(max_attempts=3)
def _deepgram_request(text: str, model: str, api_key: str, output_path: Path) -> None:
    """Make a single Deepgram TTS API request."""
    with httpx.Client(timeout=120) as client:
        response = client.post(
            DEEPGRAM_API_URL,
            params={"model": model},
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
            },
            json={"text": text},
        )
        response.raise_for_status()
        output_path.write_bytes(response.content)


def _openai_tts(text: str, output_path: Path, voice: str, settings: Settings) -> Path:
    if voice not in OPENAI_VOICES:
        voice = "onyx"

    client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())
    chunks = _chunk_text(text, max_chars=4000)

    if len(chunks) == 1:
        response = client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=chunks[0],
            response_format="mp3",
        )
        response.stream_to_file(str(output_path))
    else:
        chunk_paths: list[Path] = []
        for i, chunk in enumerate(chunks):
            chunk_path = output_path.parent / f"_chunk_{i:03d}.mp3"
            response = client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input=chunk,
                response_format="mp3",
            )
            response.stream_to_file(str(chunk_path))
            chunk_paths.append(chunk_path)

        _concat_audio(chunk_paths, output_path)

        for cp in chunk_paths:
            cp.unlink(missing_ok=True)

    return output_path


def _elevenlabs_tts(
    text: str, output_path: Path, voice: str, settings: Settings
) -> Path:
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.elevenlabs_api_key.get_secret_value())
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    return output_path


def _chunk_text(text: str, max_chars: int = 1900) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""

    for sentence in text.replace(". ", ".|").split("|"):
        if len(current) + len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
            current = sentence
        else:
            current += sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks or [text]


def _concat_audio(paths: list[Path], output: Path) -> None:
    """Concatenate audio files using ffmpeg."""
    import subprocess
    import tempfile

    list_file = Path(tempfile.mktemp(suffix=".txt"))
    list_file.write_text(
        "\n".join(f"file '{p}'" for p in paths),
        encoding="utf-8",
    )

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(output),
            ],
            capture_output=True,
            check=True,
        )
    finally:
        list_file.unlink(missing_ok=True)
