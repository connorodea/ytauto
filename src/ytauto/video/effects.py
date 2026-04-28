"""Visual effects — Ken Burns zoom/pan, section title overlays, grain overlay."""

from __future__ import annotations

import random
import subprocess
from pathlib import Path


def render_ken_burns(
    image_path: Path,
    duration: float,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    """Apply Ken Burns zoom + pan effect to a still image.

    Randomly chooses zoom-in (1.0→1.15) or zoom-out (1.15→1.0)
    with a gentle pan towards center.
    """
    total_frames = int(duration * fps)
    zoom_in = random.choice([True, False])

    if zoom_in:
        z_expr = f"min(1+0.15*on/{total_frames},1.15)"
    else:
        z_expr = f"1.15-0.15*on/{total_frames}"

    # Gentle pan towards center
    x_expr = f"iw/2-(iw/zoom/2)"
    y_expr = f"ih/2-(ih/zoom/2)"

    filter_chain = (
        f"scale={width * 2}:{height * 2},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={width}x{height}:fps={fps},"
        f"setsar=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(fps),
        "-i", str(image_path),
        "-filter_complex", filter_chain,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-t", str(duration),
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Ken Burns failed: {result.stderr[-500:]}")
    return output_path


def burn_section_titles(
    video_path: Path,
    headings: list[str],
    starts: list[float],
    durations: list[float],
    output_path: Path,
    display_duration: float = 3.0,
    fade_in: float = 0.3,
    fade_out: float = 0.5,
    font_size: int = 52,
) -> Path:
    """Burn section title overlays with fade-in/out onto a video.

    Each heading appears at the section start for `display_duration` seconds
    with alpha fade animations.
    """
    if not headings:
        # No titles to burn, just copy
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-c", "copy", str(output_path)],
            capture_output=True, check=True,
        )
        return output_path

    drawtext_filters: list[str] = []
    for heading, t_start, dur in zip(headings, starts, durations):
        t_end = t_start + min(display_duration, dur)
        fade_in_end = t_start + fade_in
        fade_out_start = t_end - fade_out

        # Escape special characters for ffmpeg drawtext
        safe_text = heading.replace("'", "\\'").replace(":", "\\:").replace("%", "%%")

        alpha_expr = (
            f"if(lt(t\\,{fade_in_end})\\,(t-{t_start})/{fade_in}\\,"
            f"if(gt(t\\,{fade_out_start})\\,({t_end}-t)/{fade_out}\\,1))"
        )

        dt = (
            f"drawtext=text='{safe_text}':"
            f"fontsize={font_size}:fontcolor=white:"
            f"x=(w-text_w)/2:y=h*0.12:"
            f"box=1:boxcolor=black@0.55:boxborderw=18:"
            f"enable='between(t,{t_start},{t_end})':"
            f"alpha='{alpha_expr}'"
        )
        drawtext_filters.append(dt)

    vf = ",".join(drawtext_filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Section titles failed: {result.stderr[-500:]}")
    return output_path


def apply_grain_overlay(
    video_path: Path,
    grain_path: Path,
    output_path: Path,
    opacity: float = 0.3,
) -> Path:
    """Apply a looped grain/VHS/scratch overlay to a video.

    The overlay is looped to match video duration, scaled to resolution,
    and blended at the specified opacity.
    """
    # Get video duration
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())

    filter_complex = (
        f"[1:v]scale=1920:1080,setpts=N/FRAME_RATE/TB,"
        f"colorchannelmixer=aa={opacity}[grain];"
        f"[0:v][grain]overlay=shortest=1[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1",
        "-i", str(grain_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Grain overlay failed: {result.stderr[-500:]}")
    return output_path
