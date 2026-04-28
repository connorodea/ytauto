"""Video assembly service using ffmpeg subprocess calls."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ytauto.config.settings import Settings


def check_ffmpeg() -> str | None:
    """Return the ffmpeg path if available, None otherwise."""
    return shutil.which("ffmpeg")


def get_audio_duration(audio_path: Path) -> float:
    """Get the duration of an audio file in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def assemble_video(
    image_paths: list[Path],
    voiceover_path: Path,
    output_path: Path,
    settings: Settings | None = None,
    background_music_path: Path | None = None,
) -> Path:
    """Assemble a video from images + voiceover + optional background music.

    Creates a slideshow video where each image is shown for a calculated duration
    to match the voiceover length, then mixes in audio.

    Returns the path to the final video.
    """
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    if not check_ffmpeg():
        raise RuntimeError("ffmpeg not found. Install it: https://ffmpeg.org/download.html")

    if not image_paths:
        raise ValueError("No images provided for video assembly.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get voiceover duration to calculate per-image timing
    audio_duration = get_audio_duration(voiceover_path)
    image_duration = max(3, audio_duration / len(image_paths))

    # Parse resolution
    res = settings.default_resolution.split("x")
    width, height = int(res[0]), int(res[1])

    # Build image input list file for ffmpeg concat demuxer
    concat_file = output_path.parent / "_image_list.txt"
    lines: list[str] = []
    for img in image_paths:
        lines.append(f"file '{img}'")
        lines.append(f"duration {image_duration:.2f}")
    # Repeat last image to avoid ffmpeg cutting it short
    if image_paths:
        lines.append(f"file '{image_paths[-1]}'")
    concat_file.write_text("\n".join(lines), encoding="utf-8")

    # Build ffmpeg command
    music_volume = settings.default_music_volume

    if background_music_path and background_music_path.exists():
        # Full pipeline: images + voiceover + background music
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(voiceover_path),
            "-i", str(background_music_path),
            "-filter_complex",
            (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v];"
                f"[2:a]volume={music_volume}[music];"
                f"[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[a]"
            ),
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", str(settings.default_fps),
            "-shortest",
            str(output_path),
        ]
    else:
        # Images + voiceover only
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(voiceover_path),
            "-filter_complex",
            (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v]"
            ),
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", str(settings.default_fps),
            "-shortest",
            str(output_path),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Clean up temp file
    concat_file.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")

    return output_path
