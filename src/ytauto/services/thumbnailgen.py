"""Thumbnail generation — delegates to imagegen.generate_thumbnail."""

from __future__ import annotations

from pathlib import Path

from ytauto.config.settings import Settings
from ytauto.services.imagegen import generate_thumbnail as _gen_thumb


def generate_thumbnail(
    title: str,
    topic: str,
    output_path: Path,
    settings: Settings | None = None,
) -> Path:
    """Generate a YouTube thumbnail. Thin wrapper for consistent service API."""
    return _gen_thumb(title=title, topic=topic, output_path=output_path, settings=settings)
