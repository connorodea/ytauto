"""Video transitions — crossfade, slide, fade-black, cut."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

TRANSITION_TYPES = ("crossfade", "slide_left", "slide_right", "fade_black", "cut")
DEFAULT_TRANSITION_DURATION = 0.5


def join_clips_with_transition(
    clip_paths: list[Path],
    output_path: Path,
    transition: str = "crossfade",
    transition_duration: float = DEFAULT_TRANSITION_DURATION,
) -> Path:
    """Join multiple video clips with the specified transition effect.

    Args:
        clip_paths: Ordered list of clip file paths.
        transition: One of: crossfade, slide_left, slide_right, fade_black, cut.
        transition_duration: Duration of the transition overlap in seconds.
    """
    if not clip_paths:
        raise ValueError("No clips to join.")

    if len(clip_paths) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(clip_paths[0]), "-c", "copy", str(output_path)],
            capture_output=True, check=True,
        )
        return output_path

    if transition == "cut":
        return _concat_cut(clip_paths, output_path)
    elif transition == "fade_black":
        return _fade_black(clip_paths, output_path, transition_duration)
    else:
        return _xfade_transition(clip_paths, output_path, transition, transition_duration)


def _xfade_transition(
    clips: list[Path],
    output: Path,
    transition: str,
    duration: float,
) -> Path:
    """Apply xfade transitions (crossfade, slide_left, slide_right)."""
    xfade_name = {
        "crossfade": "fade",
        "slide_left": "slideleft",
        "slide_right": "slideright",
    }.get(transition, "fade")

    # Get durations of each clip
    durations = [_get_duration(p) for p in clips]

    # Build input args
    inputs: list[str] = []
    for p in clips:
        inputs.extend(["-i", str(p)])

    # Build xfade filter chain
    # For N clips, we need N-1 xfade filters chained together
    filter_parts: list[str] = []
    offset_acc = durations[0] - duration

    if len(clips) == 2:
        filter_parts.append(
            f"[0:v][1:v]xfade=transition={xfade_name}:duration={duration}:offset={offset_acc:.3f}[outv]"
        )
    else:
        # First pair
        filter_parts.append(
            f"[0:v][1:v]xfade=transition={xfade_name}:duration={duration}:offset={offset_acc:.3f}[v1]"
        )
        for i in range(2, len(clips)):
            offset_acc += durations[i - 1] - duration
            prev = f"[v{i - 1}]"
            out = "[outv]" if i == len(clips) - 1 else f"[v{i}]"
            filter_parts.append(
                f"{prev}[{i}:v]xfade=transition={xfade_name}:duration={duration}:offset={offset_acc:.3f}{out}"
            )

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"xfade transition failed: {result.stderr[-500:]}")
    return output


def _fade_black(clips: list[Path], output: Path, fade_dur: float) -> Path:
    """Apply fade-in/out through black on each clip, then concatenate."""
    faded_clips: list[Path] = []

    for i, clip in enumerate(clips):
        duration = _get_duration(clip)
        faded = output.parent / f"_faded_{i:03d}.mp4"

        fade_out_start = max(0, duration - fade_dur)
        vf = f"fade=type=in:start_time=0:duration={fade_dur},fade=type=out:start_time={fade_out_start:.3f}:duration={fade_dur}"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(clip),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-an",
            str(faded),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        faded_clips.append(faded)

    result = _concat_cut(faded_clips, output)

    for f in faded_clips:
        f.unlink(missing_ok=True)

    return result


def _concat_cut(clips: list[Path], output: Path) -> Path:
    """Hard-cut concatenation using concat demuxer."""
    list_file = Path(tempfile.mktemp(suffix=".txt", dir=str(output.parent)))
    list_file.write_text(
        "\n".join(f"file '{p}'" for p in clips),
        encoding="utf-8",
    )

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-an",
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Concat failed: {result.stderr[-500:]}")
    finally:
        list_file.unlink(missing_ok=True)

    return output


def _get_duration(path: Path) -> float:
    """Get media file duration in seconds."""
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
