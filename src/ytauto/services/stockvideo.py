"""Stock video sourcing from Pexels API — downloads cinematic clips for Shorts."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ytauto.config.settings import Settings
from ytauto.services.retry import retry

logger = logging.getLogger(__name__)

PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"


@retry(max_attempts=3)
def search_videos(
    query: str,
    api_key: str,
    count: int = 3,
    orientation: str = "landscape",
    min_duration: int = 5,
    max_duration: int = 30,
) -> list[dict]:
    """Search Pexels for stock video clips.

    Returns list of dicts with: id, url, download_url, width, height, duration.
    """
    with httpx.Client(timeout=30) as client:
        response = client.get(
            PEXELS_VIDEO_SEARCH,
            params={
                "query": query,
                "per_page": count * 2,  # Fetch extra to filter
                "orientation": orientation,
                "size": "medium",
            },
            headers={"Authorization": api_key},
        )
        response.raise_for_status()
        data = response.json()

    results: list[dict] = []
    for video in data.get("videos", []):
        duration = video.get("duration", 0)
        if duration < min_duration or duration > max_duration:
            continue

        # Find best quality file (HD preferred)
        files = video.get("video_files", [])
        best = None
        for f in files:
            w = f.get("width", 0)
            h = f.get("height", 0)
            # Prefer HD landscape (1280x720 or 1920x1080)
            if w >= 1280 and h >= 720:
                if best is None or w > best.get("width", 0):
                    best = f

        if not best and files:
            best = max(files, key=lambda f: f.get("width", 0))

        if best:
            results.append({
                "id": video["id"],
                "url": video.get("url", ""),
                "download_url": best.get("link", ""),
                "width": best.get("width", 0),
                "height": best.get("height", 0),
                "duration": duration,
                "photographer": video.get("user", {}).get("name", "Pexels"),
            })

        if len(results) >= count:
            break

    return results


@retry(max_attempts=2)
def download_video(url: str, output_path: Path) -> Path:
    """Download a video file from URL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        output_path.write_bytes(response.content)
    return output_path


def source_clips_for_shorts(
    sections: list[dict],
    output_dir: Path,
    settings: Settings | None = None,
) -> list[Path]:
    """Source stock video clips for each section of a Shorts script.

    Uses section narration to generate search queries for cinematic B-roll.
    Returns list of downloaded clip paths.
    """
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    api_key = settings.pexels_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError(
            "Pexels API key required for stock video. "
            "Run 'ytauto setup' or set YTAUTO_PEXELS_API_KEY."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []

    # Generate search queries from sections
    for i, section in enumerate(sections):
        narration = section.get("narration", "")
        visual = section.get("visual_query", "")

        # Build a cinematic search query
        if visual:
            query = visual
        else:
            # Extract key concepts from narration
            words = narration.lower().split()
            # Map common business/motivational words to cinematic queries
            query_map = {
                "money": "business money luxury",
                "success": "successful businessman suit",
                "win": "victory celebration business",
                "client": "business meeting handshake",
                "close": "deal handshake corporate",
                "power": "powerful businessman walking",
                "hustle": "entrepreneur working late night",
                "rich": "luxury lifestyle wealth",
                "fail": "dramatic storm dark clouds",
                "secret": "mystery dark cinematic",
                "million": "money cash luxury cars",
                "strategy": "chess strategy thinking",
                "leader": "leadership corporate office",
                "market": "stock market trading screen",
                "invest": "investment finance graphs",
            }

            query = "cinematic business dramatic"
            for word in words:
                clean = word.strip(".,!?;:'\"()[]")
                if clean in query_map:
                    query = query_map[clean]
                    break

        logger.info("Searching Pexels for section %d: %s", i, query)

        try:
            results = search_videos(query, api_key, count=1)
            if results:
                clip_url = results[0]["download_url"]
                clip_path = output_dir / f"clip_{i:03d}.mp4"
                download_video(clip_url, clip_path)
                clip_paths.append(clip_path)
                logger.info("Downloaded clip %d: %s", i, clip_path.name)
            else:
                # Fallback: generic cinematic query
                fallback_results = search_videos(
                    "cinematic dark dramatic business", api_key, count=1,
                )
                if fallback_results:
                    clip_url = fallback_results[0]["download_url"]
                    clip_path = output_dir / f"clip_{i:03d}.mp4"
                    download_video(clip_url, clip_path)
                    clip_paths.append(clip_path)
        except Exception as exc:
            logger.warning("Failed to source clip for section %d: %s", i, exc)

    return clip_paths
