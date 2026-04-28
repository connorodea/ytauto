"""Clip ripper — download YouTube videos, strip overlays, split into clean clips.

Downloads a video (e.g., from a faceless motivation channel using Suits clips),
strips the added voiceover/music/text, detects scene cuts, and saves each
individual movie clip to the library.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def rip_clips(
    url: str,
    clips_dir: Path,
    tags: list[str] | None = None,
    min_clip_duration: float = 2.0,
    max_clip_duration: float = 30.0,
    scene_threshold: float = 0.3,
    strip_audio: bool = True,
) -> list[dict]:
    """Download a video and split it into individual scene clips.

    This is designed for ripping clean movie/TV footage from faceless
    motivational channels. It:
    1. Downloads the video via yt-dlp
    2. Strips the audio track (removes voiceover/music overlay)
    3. Detects scene cuts using ffmpeg scene detection
    4. Splits into individual clips at each cut point
    5. Saves each clip to the library

    Args:
        url: YouTube URL to download.
        clips_dir: Directory to store extracted clips.
        tags: Tags to apply to all extracted clips.
        min_clip_duration: Skip clips shorter than this (seconds).
        max_clip_duration: Cap clips at this duration.
        scene_threshold: Scene change detection sensitivity (0.0-1.0).
            Lower = more sensitive, more cuts detected.
            Default 0.3 works well for hard cuts between movie scenes.
        strip_audio: If True, remove audio track (removes voiceover/music).

    Returns:
        List of clip metadata dicts saved to library.
    """
    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        raise RuntimeError("yt-dlp not found. Install: pip install yt-dlp")

    clips_dir.mkdir(parents=True, exist_ok=True)
    work_dir = clips_dir / "_rip_work"
    work_dir.mkdir(exist_ok=True)

    # ── Step 1: Download ─────────────────────────────────────────────────
    dl_path = work_dir / "source.mp4"
    dl_result = subprocess.run(
        [
            yt_dlp,
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", str(dl_path),
            "--no-playlist",
            "--no-warnings",
            url,
        ],
        capture_output=True, text=True, timeout=300,
    )
    if dl_result.returncode != 0:
        raise RuntimeError(f"Download failed: {dl_result.stderr[:300]}")

    if not dl_path.exists():
        # yt-dlp might add extension
        candidates = list(work_dir.glob("source*"))
        if candidates:
            dl_path = candidates[0]
        else:
            raise RuntimeError("Download completed but file not found.")

    # Get video title from yt-dlp
    title = "unknown"
    try:
        meta_result = subprocess.run(
            [yt_dlp, "--dump-json", "--no-warnings", url],
            capture_output=True, text=True, timeout=30,
        )
        if meta_result.returncode == 0:
            meta = json.loads(meta_result.stdout)
            title = meta.get("title", "unknown")
    except Exception:
        pass

    # ── Step 2: Strip audio (optional) ───────────────────────────────────
    if strip_audio:
        stripped = work_dir / "stripped.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(dl_path), "-an", "-c:v", "copy", str(stripped)],
            capture_output=True, check=True,
        )
        source = stripped
    else:
        source = dl_path

    # ── Step 3: Detect scene cuts ────────────────────────────────────────
    scene_times = _detect_scenes(source, scene_threshold)

    if not scene_times:
        # No scenes detected — treat whole video as one clip
        scene_times = [0.0]

    # Add video end time
    duration = _get_duration(source)
    scene_times.append(duration)

    # ── Step 4: Split into clips ─────────────────────────────────────────
    from ytauto.services.clips import _load_index, _save_index

    index = _load_index(clips_dir)
    extracted: list[dict] = []

    for i in range(len(scene_times) - 1):
        start = scene_times[i]
        end = scene_times[i + 1]
        clip_dur = end - start

        # Skip too short or too long
        if clip_dur < min_clip_duration:
            continue
        if clip_dur > max_clip_duration:
            end = start + max_clip_duration
            clip_dur = max_clip_duration

        clip_id = uuid.uuid4().hex[:10]
        clip_name = f"{clip_id}_rip_{i + 1:03d}.mp4"
        clip_path = clips_dir / clip_name

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-to", str(end),
            "-i", str(source),
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-pix_fmt", "yuv420p",
        ]
        if strip_audio:
            cmd.append("-an")
        else:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        cmd.append(str(clip_path))

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            continue

        meta = {
            "id": clip_id,
            "file": clip_name,
            "title": f"{title[:30]} scene {i + 1}",
            "source": title,
            "source_url": url,
            "duration": round(clip_dur, 1),
            "tags": tags or [],
        }
        index.append(meta)
        extracted.append(meta)

    _save_index(clips_dir, index)

    # ── Cleanup ──────────────────────────────────────────────────────────
    shutil.rmtree(work_dir, ignore_errors=True)

    return extracted


def _detect_scenes(video_path: Path, threshold: float = 0.3) -> list[float]:
    """Detect scene change timestamps using ffmpeg's scene filter.

    Returns a sorted list of timestamps (in seconds) where cuts are detected.
    """
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr",
        "-f", "null",
        "-",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # Parse timestamps from showinfo output in stderr
    timestamps: list[float] = [0.0]
    for line in result.stderr.split("\n"):
        if "pts_time:" in line:
            try:
                # Extract pts_time value
                pts_part = line.split("pts_time:")[1].split()[0]
                t = float(pts_part)
                timestamps.append(t)
            except (IndexError, ValueError):
                continue

    return sorted(set(timestamps))


def _get_duration(path: Path) -> float:
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
