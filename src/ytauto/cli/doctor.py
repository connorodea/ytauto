"""Doctor command — check environment dependencies and configuration."""

from __future__ import annotations

import platform
import shutil
import sys

import typer

from ytauto.cli.theme import console, error, header, success, warning
from ytauto.config.settings import get_settings


def doctor() -> None:
    """Check that all dependencies and API keys are configured correctly."""
    settings = get_settings()
    issues = 0

    console.print()
    console.print(header("Environment Check"))
    console.print()

    # Python
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        success(f"Python {py_ver}")
    else:
        error(f"Python {py_ver} — requires 3.11+")
        issues += 1

    # ffmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        success(f"ffmpeg found at {ffmpeg_path}")
    else:
        error("ffmpeg not found — required for video rendering")
        console.print("    [dim]Install: https://ffmpeg.org/download.html[/dim]")
        issues += 1

    # ffprobe
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        success(f"ffprobe found at {ffprobe_path}")
    else:
        error("ffprobe not found — required for audio duration detection")
        issues += 1

    # API Keys
    console.print()

    if settings.has_anthropic():
        success("Anthropic API key configured")
    else:
        warning("Anthropic API key not set (needed for Claude script generation)")
        issues += 1

    if settings.has_openai():
        success("OpenAI API key configured")
    else:
        warning("OpenAI API key not set (needed for TTS and image generation)")
        issues += 1

    if settings.has_elevenlabs():
        success("ElevenLabs API key configured")
    else:
        console.print("  [dim]\u2022 ElevenLabs API key not set (optional — premium voices)[/dim]")

    # Data directory
    console.print()
    data_dir = settings.data_dir
    if data_dir.exists():
        success(f"Data directory exists: {data_dir}")
    else:
        warning(f"Data directory missing: {data_dir} (will be created on first run)")

    # Disk space
    try:
        import os
        stat = os.statvfs(str(data_dir.parent))
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        if free_gb > 5:
            success(f"{free_gb:.0f} GB free disk space")
        else:
            warning(f"Only {free_gb:.1f} GB free — videos can be large")
            issues += 1
    except Exception:
        pass

    # Summary
    console.print()
    if issues == 0:
        success("[bold]All checks passed![/bold] You're ready to create videos.\n")
    else:
        warning(f"[bold]{issues} issue(s) found.[/bold] Run [accent]ytauto setup[/accent] to configure missing keys.\n")
