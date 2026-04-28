"""Video cropping and reformatting — landscape to vertical 9:16."""

from __future__ import annotations

import subprocess
from pathlib import Path


def crop_to_vertical(
    input_path: Path,
    output_path: Path,
    target_width: int = 1080,
    target_height: int = 1920,
    duration: float | None = None,
) -> Path:
    """Center-crop a landscape video to 9:16 vertical format.

    Crops the center third of the frame horizontally, then scales to target.
    """
    # Get input dimensions
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            str(input_path),
        ],
        capture_output=True, text=True, check=True,
    )
    parts = probe.stdout.strip().split(",")
    in_w, in_h = int(parts[0]), int(parts[1])

    # Calculate crop dimensions to get 9:16 from center
    # Target aspect = 9/16 = 0.5625
    target_aspect = target_width / target_height
    crop_w = int(in_h * target_aspect)
    crop_h = in_h
    crop_x = (in_w - crop_w) // 2

    # Ensure crop doesn't exceed input
    if crop_w > in_w:
        crop_w = in_w
        crop_h = int(in_w / target_aspect)
        crop_x = 0

    vf = (
        f"crop={crop_w}:{crop_h}:{crop_x}:0,"
        f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
        f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",  # Strip audio — we'll add our own voiceover
    ]

    if duration:
        cmd.extend(["-t", str(duration)])

    cmd.append(str(output_path))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Crop failed: {result.stderr[-500:]}")

    return output_path


def get_video_duration(path: Path) -> float:
    """Get video duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())
