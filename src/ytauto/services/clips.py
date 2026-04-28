"""Clip library — download, organize, and manage video clips for Shorts.

Downloads movie/TV clips from YouTube via yt-dlp and organizes them into
a local library for use in faceless Shorts. Clips are stored at
~/.ytauto/clips/ and tagged with metadata for smart matching.
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

CLIPS_DIR_NAME = "clips"
METADATA_FILE = "clips_index.json"


def get_clips_dir(data_dir: Path | None = None) -> Path:
    """Get the clips library directory, creating it if needed."""
    if data_dir is None:
        from ytauto.config.settings import get_settings
        data_dir = get_settings().data_dir
    clips_dir = data_dir / CLIPS_DIR_NAME
    clips_dir.mkdir(parents=True, exist_ok=True)
    return clips_dir


def _load_index(clips_dir: Path) -> list[dict]:
    """Load the clip metadata index."""
    index_path = clips_dir / METADATA_FILE
    if index_path.exists():
        return json.loads(index_path.read_text(encoding="utf-8"))
    return []


def _save_index(clips_dir: Path, index: list[dict]) -> None:
    """Save the clip metadata index."""
    index_path = clips_dir / METADATA_FILE
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def download_clip(
    url: str,
    clips_dir: Path | None = None,
    tags: list[str] | None = None,
    max_duration: int = 120,
) -> dict:
    """Download a video clip from YouTube via yt-dlp.

    Args:
        url: YouTube URL (full video, Short, or clip URL).
        clips_dir: Directory to store clips. Defaults to ~/.ytauto/clips/.
        tags: Optional tags for categorization (e.g., ["suits", "business", "drama"]).
        max_duration: Skip videos longer than this (seconds).

    Returns:
        Clip metadata dict with: id, file, title, source, duration, tags.
    """
    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        raise RuntimeError(
            "yt-dlp not found. Install it:\n"
            "  brew install yt-dlp  OR  pip install yt-dlp"
        )

    clips_dir = clips_dir or get_clips_dir()
    clip_id = uuid.uuid4().hex[:10]

    # Get metadata first
    meta_result = subprocess.run(
        [yt_dlp, "--dump-json", "--no-warnings", url],
        capture_output=True, text=True, timeout=30,
    )
    if meta_result.returncode != 0:
        raise RuntimeError(f"Failed to fetch video info: {meta_result.stderr[:300]}")

    meta = json.loads(meta_result.stdout)
    title = meta.get("title", "untitled")
    duration = meta.get("duration", 0)
    channel = meta.get("channel", "unknown")

    if duration > max_duration:
        raise ValueError(
            f"Video is {duration}s — exceeds {max_duration}s limit. "
            f"Use a shorter clip or increase --max-duration."
        )

    # Download as MP4, best quality ≤1080p
    output_template = str(clips_dir / f"{clip_id}_%(title).40s.%(ext)s")
    dl_result = subprocess.run(
        [
            yt_dlp,
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", output_template,
            "--no-playlist",
            "--no-warnings",
            url,
        ],
        capture_output=True, text=True, timeout=300,
    )
    if dl_result.returncode != 0:
        raise RuntimeError(f"Download failed: {dl_result.stderr[:300]}")

    # Find the downloaded file
    downloaded = list(clips_dir.glob(f"{clip_id}_*"))
    if not downloaded:
        raise RuntimeError("Download completed but file not found.")

    clip_file = downloaded[0]

    # Build metadata entry
    clip_meta = {
        "id": clip_id,
        "file": clip_file.name,
        "title": title,
        "source": channel,
        "source_url": url,
        "duration": duration,
        "tags": tags or [],
    }

    # Add to index
    index = _load_index(clips_dir)
    index.append(clip_meta)
    _save_index(clips_dir, index)

    return clip_meta


def import_folder(
    folder: Path,
    clips_dir: Path | None = None,
    tags: list[str] | None = None,
) -> list[dict]:
    """Import all video files from a folder into the clip library.

    Copies files into the clips directory and indexes them.
    """
    clips_dir = clips_dir or get_clips_dir()
    index = _load_index(clips_dir)
    imported: list[dict] = []

    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in video_exts:
            continue

        clip_id = uuid.uuid4().hex[:10]
        dest = clips_dir / f"{clip_id}_{f.stem[:40]}{f.suffix}"
        shutil.copy2(f, dest)

        # Get duration
        duration = 0
        try:
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(dest),
                ],
                capture_output=True, text=True, timeout=10,
            )
            duration = float(probe.stdout.strip())
        except Exception:
            pass

        meta = {
            "id": clip_id,
            "file": dest.name,
            "title": f.stem,
            "source": "local",
            "source_url": str(f),
            "duration": duration,
            "tags": tags or [],
        }
        index.append(meta)
        imported.append(meta)

    _save_index(clips_dir, index)
    return imported


def extract_clips(
    video_path: Path,
    timestamps: list[tuple[str, str]],
    clips_dir: Path | None = None,
    tags: list[str] | None = None,
    source_name: str = "local",
) -> list[dict]:
    """Extract multiple short clips from a long video file.

    Args:
        video_path: Path to the source video (movie episode, etc.).
        timestamps: List of (start, end) tuples as "HH:MM:SS" or "MM:SS" strings.
        clips_dir: Output directory. Defaults to ~/.ytauto/clips/.
        tags: Tags for all extracted clips.
        source_name: Label for the source (e.g., "Suits S01E01").

    Returns:
        List of clip metadata dicts.
    """
    clips_dir = clips_dir or get_clips_dir()
    index = _load_index(clips_dir)
    extracted: list[dict] = []

    video_title = video_path.stem

    for i, (start, end) in enumerate(timestamps):
        clip_id = uuid.uuid4().hex[:10]
        clip_name = f"{clip_id}_{video_title[:30]}_clip{i + 1:02d}.mp4"
        output = clips_dir / clip_name

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", start,
                "-to", end,
                "-i", str(video_path),
                "-c:v", "libx264", "-crf", "20", "-preset", "fast",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                str(output),
            ],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            logger.warning("Failed to extract clip %d: %s", i + 1, result.stderr[:200])
            continue

        # Get duration
        duration = 0
        try:
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(output),
                ],
                capture_output=True, text=True, timeout=10,
            )
            duration = float(probe.stdout.strip())
        except Exception:
            pass

        meta = {
            "id": clip_id,
            "file": clip_name,
            "title": f"{source_name} clip {i + 1}",
            "source": source_name,
            "source_url": str(video_path),
            "duration": duration,
            "tags": tags or [],
        }
        index.append(meta)
        extracted.append(meta)

    _save_index(clips_dir, index)
    return extracted


def list_clips(clips_dir: Path | None = None, tag: str | None = None) -> list[dict]:
    """List all clips in the library, optionally filtered by tag."""
    clips_dir = clips_dir or get_clips_dir()
    index = _load_index(clips_dir)

    if tag:
        index = [c for c in index if tag.lower() in [t.lower() for t in c.get("tags", [])]]

    return index


def select_clips_for_sections(
    sections: list[dict],
    clips_dir: Path | None = None,
    tag: str | None = None,
) -> list[Path]:
    """Select random clips from the library for each section.

    Returns one clip path per section, cycling if there are fewer clips
    than sections.
    """
    clips_dir = clips_dir or get_clips_dir()
    available = list_clips(clips_dir, tag=tag)

    if not available:
        raise RuntimeError(
            "No clips in library. Add some with:\n"
            "  ytauto clips-add <youtube-url>\n"
            "  ytauto clips-import <folder>"
        )

    # Shuffle and cycle through available clips
    random.shuffle(available)
    paths: list[Path] = []

    for i in range(len(sections)):
        clip = available[i % len(available)]
        clip_path = clips_dir / clip["file"]
        if clip_path.exists():
            paths.append(clip_path)
        else:
            # Fallback to any existing clip
            for c in available:
                p = clips_dir / c["file"]
                if p.exists():
                    paths.append(p)
                    break

    return paths


def delete_clip(clip_id: str, clips_dir: Path | None = None) -> bool:
    """Delete a clip from the library by ID."""
    clips_dir = clips_dir or get_clips_dir()
    index = _load_index(clips_dir)

    found = None
    for i, clip in enumerate(index):
        if clip["id"] == clip_id:
            found = i
            break

    if found is None:
        return False

    clip = index.pop(found)
    clip_path = clips_dir / clip["file"]
    clip_path.unlink(missing_ok=True)
    _save_index(clips_dir, index)
    return True
