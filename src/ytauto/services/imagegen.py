"""Image generation service using DALL-E."""

from __future__ import annotations

from pathlib import Path

import httpx
import openai

from ytauto.config.settings import Settings
from ytauto.services.retry import retry


def generate_images(
    sections: list[dict],
    output_dir: Path,
    settings: Settings | None = None,
) -> list[Path]:
    """Generate one image per script section using DALL-E.

    Args:
        sections: List of dicts with at minimum a "visual_prompt" key.
        output_dir: Directory to save generated images.

    Returns:
        List of paths to generated images.
    """
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    if not settings.has_openai():
        raise RuntimeError("OpenAI API key required for image generation. Run 'ytauto setup'.")

    output_dir.mkdir(parents=True, exist_ok=True)
    client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())
    paths: list[Path] = []

    for i, section in enumerate(sections):
        prompt = section.get("visual_prompt", section.get("heading", "abstract background"))
        full_prompt = (
            f"Cinematic 16:9 YouTube video frame, dark dramatic lighting, "
            f"professional production quality: {prompt}"
        )

        image_path = output_dir / f"section_{i:03d}.png"
        _generate_single_image(client, full_prompt, image_path)
        paths.append(image_path)

    return paths


def generate_thumbnail(
    title: str,
    topic: str,
    output_path: Path,
    settings: Settings | None = None,
) -> Path:
    """Generate a YouTube thumbnail image using DALL-E.

    Returns the path to the generated thumbnail.
    """
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    if not settings.has_openai():
        raise RuntimeError("OpenAI API key required for thumbnails. Run 'ytauto setup'.")

    client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())

    prompt = (
        f"YouTube thumbnail, ultra high contrast, bold dramatic composition, "
        f"dark cinematic background with vibrant accent colors, "
        f"visually striking and clickable, topic: {topic}. "
        f"NO TEXT in the image — clean visual only. "
        f"Professional, high-production-value look."
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _generate_single_image(client, prompt, output_path)
    return output_path


@retry(max_attempts=3)
def _generate_single_image(client: openai.OpenAI, prompt: str, output_path: Path) -> None:
    """Generate a single image via DALL-E with retry on transient failures."""
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt[:4000],
        size="1792x1024",
        quality="hd",
        n=1,
    )

    image_url = response.data[0].url

    with httpx.Client(timeout=60) as http:
        img_response = http.get(image_url)
        img_response.raise_for_status()
        output_path.write_bytes(img_response.content)
