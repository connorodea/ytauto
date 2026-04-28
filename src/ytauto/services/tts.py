"""Text-to-speech service using OpenAI TTS or ElevenLabs."""

from __future__ import annotations

from pathlib import Path

import openai

from ytauto.config.settings import Settings

OPENAI_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")


def synthesize_voiceover(
    text: str,
    output_path: Path,
    voice: str = "onyx",
    settings: Settings | None = None,
) -> Path:
    """Generate speech audio from text.

    Returns the path to the generated audio file.
    """
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    provider = settings.default_tts_provider

    if provider == "elevenlabs" and settings.has_elevenlabs():
        return _elevenlabs_tts(text, output_path, voice, settings)
    elif settings.has_openai():
        return _openai_tts(text, output_path, voice, settings)
    else:
        raise RuntimeError("No TTS API key configured. Run 'ytauto setup'.")


def _openai_tts(text: str, output_path: Path, voice: str, settings: Settings) -> Path:
    if voice not in OPENAI_VOICES:
        voice = "onyx"

    client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())

    # OpenAI TTS has a 4096 char limit per request — chunk if needed
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
        # Generate chunks and concatenate with ffmpeg
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


def _chunk_text(text: str, max_chars: int = 4000) -> list[str]:
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
