"""Video assembly service — enhanced with Ken Burns, transitions, and effects."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ytauto.config.settings import Settings


def check_ffmpeg() -> str | None:
    """Return the ffmpeg path if available, None otherwise."""
    return shutil.which("ffmpeg")


def _has_filter(name: str) -> bool:
    """Check if an ffmpeg filter is available (e.g., drawtext, ass, subtitles)."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-filters"],
            capture_output=True, text=True,
        )
        return f" {name} " in result.stdout or f" {name}\n" in result.stdout
    except Exception:
        return False


def get_audio_duration(audio_path: Path) -> float:
    """Get the duration of an audio file in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def assemble_video(
    image_paths: list[Path],
    voiceover_path: Path,
    output_path: Path,
    settings: Settings | None = None,
    background_music_path: Path | None = None,
    transition: str = "crossfade",
    ken_burns: bool = True,
    section_headings: list[str] | None = None,
    caption_style: str | None = None,
    word_timestamps: list[dict] | None = None,
    grain_path: Path | None = None,
) -> Path:
    """Assemble a production-quality video with effects.

    Pipeline:
    1. Render each image with Ken Burns effect (if enabled)
    2. Join clips with transitions (crossfade, slide, fade_black, cut)
    3. Mix voiceover + background music (with fades and normalization)
    4. Mux video + audio
    5. Burn section title overlays (if provided)
    6. Burn captions (if word timestamps provided)
    7. Apply grain overlay (if provided)
    """
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    if not check_ffmpeg():
        raise RuntimeError("ffmpeg not found. Install it: https://ffmpeg.org/download.html")

    if not image_paths:
        raise ValueError("No images provided for video assembly.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output_path.parent
    res = settings.default_resolution.split("x")
    width, height = int(res[0]), int(res[1])
    fps = settings.default_fps

    # Get voiceover duration for timing calculations
    audio_duration = get_audio_duration(voiceover_path)
    image_duration = max(3.0, audio_duration / len(image_paths))

    # ── Step 1: Render each image as a clip ──────────────────────────────
    clip_paths: list[Path] = []
    for i, img in enumerate(image_paths):
        clip_path = work_dir / f"_clip_{i:03d}.mp4"
        if ken_burns:
            from ytauto.video.effects import render_ken_burns
            render_ken_burns(img, image_duration, clip_path, width, height, fps)
        else:
            _render_static_clip(img, image_duration, clip_path, width, height, fps)
        clip_paths.append(clip_path)

    # ── Step 2: Join clips with transitions ──────────────────────────────
    joined_path = work_dir / "_joined.mp4"
    from ytauto.video.transitions import join_clips_with_transition
    join_clips_with_transition(clip_paths, joined_path, transition=transition)

    # ── Step 3: Mix audio ────────────────────────────────────────────────
    if background_music_path and background_music_path.exists():
        mixed_audio = work_dir / "_mixed_audio.aac"
        from ytauto.video.audio import mix_voiceover_and_music
        mix_voiceover_and_music(
            voiceover_path, background_music_path, mixed_audio,
            music_volume=settings.default_music_volume,
        )
        audio_source = mixed_audio
    else:
        audio_source = voiceover_path

    # ── Step 4: Mux video + audio ────────────────────────────────────────
    muxed_path = work_dir / "_muxed.mp4"
    _mux_video_audio(joined_path, audio_source, muxed_path)
    current = muxed_path

    # ── Step 5: Section title overlays (requires drawtext filter) ────────
    if section_headings and _has_filter("drawtext"):
        titled_path = work_dir / "_titled.mp4"
        starts = [i * image_duration for i in range(len(section_headings))]
        durations = [image_duration] * len(section_headings)
        from ytauto.video.effects import burn_section_titles
        burn_section_titles(current, section_headings, starts, durations, titled_path)
        current = titled_path

    # ── Step 6: Captions (requires ass/subtitles filter) ─────────────────
    if caption_style and word_timestamps:
        captioned_path = work_dir / "_captioned.mp4"
        ass_path = work_dir / "captions.ass"
        from ytauto.video.captions import generate_ass_captions, burn_captions
        generate_ass_captions(word_timestamps, ass_path, style=caption_style)
        if _has_filter("ass") or _has_filter("subtitles"):
            burn_captions(current, ass_path, captioned_path)
            current = captioned_path
        # ASS file is still saved even if burn fails — can be used externally

    # ── Step 7: Grain overlay ────────────────────────────────────────────
    if grain_path and grain_path.exists():
        grained_path = work_dir / "_grained.mp4"
        from ytauto.video.effects import apply_grain_overlay
        apply_grain_overlay(current, grain_path, grained_path)
        current = grained_path

    # ── Final: Move to output path ───────────────────────────────────────
    if current != output_path:
        shutil.move(str(current), str(output_path))

    # ── Cleanup temp files ───────────────────────────────────────────────
    for f in work_dir.glob("_clip_*.mp4"):
        f.unlink(missing_ok=True)
    for f in work_dir.glob("_*.mp4"):
        f.unlink(missing_ok=True)
    for f in work_dir.glob("_*.aac"):
        f.unlink(missing_ok=True)

    return output_path


def _render_static_clip(
    image_path: Path,
    duration: float,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
) -> Path:
    """Render a static image as a video clip (no Ken Burns)."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(fps),
        "-i", str(image_path),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,setsar=1",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-t", str(duration),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Static clip render failed: {result.stderr[-500:]}")
    return output_path


def _mux_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """Combine a video stream with an audio stream."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Mux failed: {result.stderr[-500:]}")
    return output_path
