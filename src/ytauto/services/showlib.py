"""Curated show library — pre-built search queries for popular shows.

Maps show names to YouTube search queries that find clean scene compilations
from official channels (no overlays, no added voiceover).
"""

from __future__ import annotations

import json
import logging
import subprocess
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Curated show sources — official channels and clean compilations
SHOW_CATALOG: dict[str, dict] = {
    "suits": {
        "name": "Suits",
        "genre": "business, law, drama",
        "vibe": "corporate power, negotiation, confidence, leadership",
        "queries": [
            "suits official harvey specter scenes",
            "suits official best scenes compilation",
            "suits official clips coffee break",
            "suits official villain defeats",
        ],
    },
    "peaky-blinders": {
        "name": "Peaky Blinders",
        "genre": "crime, drama, period",
        "vibe": "power, ambition, strategy, intimidation, loyalty",
        "queries": [
            "peaky blinders official best scenes",
            "peaky blinders thomas shelby best moments",
            "peaky blinders alfie solomons scenes",
        ],
    },
    "breaking-bad": {
        "name": "Breaking Bad",
        "genre": "crime, drama, thriller",
        "vibe": "transformation, power, consequence, risk, empire",
        "queries": [
            "breaking bad official most iconic scenes",
            "breaking bad best moments compilation",
            "breaking bad nail biting moments",
        ],
    },
    "billions": {
        "name": "Billions",
        "genre": "finance, drama, thriller",
        "vibe": "wealth, wall street, power plays, strategy, ambition",
        "queries": [
            "billions showtime intense confrontations",
            "billions best scenes compilation",
            "billions bobby axelrod scenes",
        ],
    },
    "wolf-of-wall-street": {
        "name": "Wolf of Wall Street",
        "genre": "finance, comedy, drama",
        "vibe": "hustle, money, sales, excess, motivation",
        "queries": [
            "wolf of wall street best scenes",
            "wolf of wall street jordan belfort speech",
            "wolf of wall street money scenes",
        ],
    },
    "godfather": {
        "name": "The Godfather",
        "genre": "crime, drama",
        "vibe": "power, family, loyalty, respect, leadership",
        "queries": [
            "godfather best scenes HD",
            "godfather most iconic scenes",
            "godfather part 2 best scenes",
        ],
    },
    "mad-men": {
        "name": "Mad Men",
        "genre": "drama, business",
        "vibe": "persuasion, advertising, confidence, charisma",
        "queries": [
            "mad men best moments quotes",
            "mad men don draper pitch scenes",
            "mad men best scenes compilation",
        ],
    },
    "succession": {
        "name": "Succession",
        "genre": "drama, business, family",
        "vibe": "wealth, power, dynasty, corporate warfare",
        "queries": [
            "succession best scenes HBO",
            "succession logan roy scenes",
            "succession most intense moments",
        ],
    },
    "house-of-cards": {
        "name": "House of Cards",
        "genre": "political, thriller, drama",
        "vibe": "power, manipulation, strategy, ambition",
        "queries": [
            "house of cards frank underwood scenes",
            "house of cards best monologues",
            "house of cards best scenes",
        ],
    },
    "scarface": {
        "name": "Scarface",
        "genre": "crime, drama",
        "vibe": "ambition, empire, hustle, rise and fall",
        "queries": [
            "scarface best scenes HD",
            "scarface tony montana scenes",
            "scarface iconic moments",
        ],
    },
}


def list_shows() -> list[dict]:
    """List all shows in the curated catalog."""
    return [
        {"id": k, **v}
        for k, v in SHOW_CATALOG.items()
    ]


def search_show_videos(
    show_id: str,
    max_results: int = 5,
    min_duration: int = 120,
) -> list[dict]:
    """Search YouTube for clean scene compilations for a show.

    Returns list of videos with: title, url, channel, duration, views.
    """
    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        raise RuntimeError("yt-dlp not found.")

    show = SHOW_CATALOG.get(show_id)
    if not show:
        raise ValueError(f"Unknown show: {show_id}. Available: {list(SHOW_CATALOG.keys())}")

    results: list[dict] = []
    seen_ids: set[str] = set()

    for query in show["queries"]:
        try:
            search_result = subprocess.run(
                [yt_dlp, "--dump-json", "--no-warnings", f"ytsearch5:{query}"],
                capture_output=True, text=True, timeout=30,
            )
            for line in search_result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    vid = d.get("id", "")
                    dur = d.get("duration", 0)

                    if vid in seen_ids or dur < min_duration:
                        continue
                    seen_ids.add(vid)

                    results.append({
                        "title": d.get("title", "?"),
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "channel": d.get("channel", "?"),
                        "duration": dur,
                        "views": d.get("view_count", 0),
                    })
                except json.JSONDecodeError:
                    continue
        except Exception:
            continue

        if len(results) >= max_results:
            break

    # Sort by views descending
    results.sort(key=lambda x: x.get("views", 0), reverse=True)
    return results[:max_results]
