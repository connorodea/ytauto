"""Pillow-based caption renderer — generates transparent caption overlay video.

Renders word-level animated captions as a transparent video overlay using
PIL/Pillow for text rendering, then composites onto the main video with
ffmpeg's standard overlay filter. Works on ANY ffmpeg build (no libass/
freetype required).

Style inspired by Hormozi, MrBeast, Infinite Wealth Lab — bold white text
with black outline, word-by-word highlight animation.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Caption style presets
STYLES = {
    "hormozi": {
        "font_size": 62,
        "color": (255, 255, 255),
        "highlight_color": (255, 215, 0),  # Gold
        "outline_color": (0, 0, 0),
        "outline_width": 4,
        "words_per_group": 3,
        "position": "center",  # center or bottom
        "uppercase": True,
    },
    "mrbeast": {
        "font_size": 68,
        "color": (255, 255, 255),
        "highlight_color": (255, 50, 50),  # Red
        "outline_color": (0, 0, 0),
        "outline_width": 5,
        "words_per_group": 2,
        "position": "center",
        "uppercase": True,
    },
    "tiktok": {
        "font_size": 72,
        "color": (255, 255, 255),
        "highlight_color": (0, 212, 255),  # Cyan
        "outline_color": (0, 0, 0),
        "outline_width": 5,
        "words_per_group": 2,
        "position": "center",
        "uppercase": True,
    },
    "cinematic": {
        "font_size": 44,
        "color": (255, 255, 255),
        "highlight_color": (255, 255, 255),
        "outline_color": (0, 0, 0),
        "outline_width": 2,
        "words_per_group": 5,
        "position": "bottom",
        "uppercase": False,
    },
    "minimal": {
        "font_size": 38,
        "color": (255, 255, 255),
        "highlight_color": (255, 255, 255),
        "outline_color": (0, 0, 0),
        "outline_width": 2,
        "words_per_group": 6,
        "position": "bottom",
        "uppercase": False,
    },
}


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Get a bold font, trying system fonts."""
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFCompact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default(size=size)


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    outline_color: tuple[int, int, int],
    outline_width: int,
) -> None:
    """Draw text with a thick outline (stroke)."""
    x, y = xy
    # Draw outline by rendering text at offsets
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx * dx + dy * dy <= outline_width * outline_width:
                draw.text((x + dx, y + dy), text, font=font, fill=(*outline_color, 255))
    # Draw main text on top
    draw.text((x, y), text, font=font, fill=(*fill, 255))


def _chunk_words(words: list[dict], per_group: int) -> list[list[dict]]:
    """Group words into display chunks."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for w in words:
        current.append(w)
        text = w.get("word", w.get("text", ""))
        if len(current) >= per_group or text.rstrip().endswith((".", "!", "?", ",")):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def render_caption_overlay(
    word_timestamps: list[dict],
    video_duration: float,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    style: str = "hormozi",
) -> Path:
    """Render a transparent video with animated captions.

    Creates a video of transparent PNGs with word-by-word highlighted captions,
    ready to be overlaid on the main video.
    """
    cfg = STYLES.get(style, STYLES["hormozi"])
    font = _get_font(cfg["font_size"])
    words_per_group = cfg["words_per_group"]
    is_upper = cfg["uppercase"]

    chunks = _chunk_words(word_timestamps, words_per_group)
    total_frames = int(video_duration * fps)

    # Pre-compute which chunk is active at each time
    chunk_times: list[tuple[float, float, list[dict]]] = []
    for chunk in chunks:
        if not chunk:
            continue
        start = chunk[0].get("start", 0)
        end = chunk[-1].get("end", start + 0.5)
        chunk_times.append((start, end, chunk))

    # Render frames to a temp directory
    frames_dir = output_path.parent / "_caption_frames"
    frames_dir.mkdir(exist_ok=True)

    logger.info("Rendering %d caption frames at %dx%d", total_frames, width, height)

    for frame_idx in range(total_frames):
        t = frame_idx / fps

        # Create transparent frame
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        # Find active chunk
        active_chunk = None
        for c_start, c_end, chunk in chunk_times:
            if c_start <= t < c_end:
                active_chunk = (c_start, c_end, chunk)
                break

        if active_chunk:
            c_start, c_end, chunk = active_chunk
            draw = ImageDraw.Draw(img)

            # Build display text
            words_text = []
            for w in chunk:
                word = w.get("word", w.get("text", ""))
                if is_upper:
                    word = word.upper()
                words_text.append(word)

            full_text = " ".join(words_text)

            # Auto-wrap for vertical video
            lines: list[str] = []
            current_line = ""
            for word in words_text:
                test = f"{current_line} {word}".strip()
                bbox = font.getbbox(test)
                text_width = bbox[2] - bbox[0]
                if text_width > width - 80 and current_line:
                    lines.append(current_line)
                    current_line = word
                else:
                    current_line = test
            if current_line:
                lines.append(current_line)

            # Calculate total text height
            line_height = cfg["font_size"] + 12
            total_text_height = len(lines) * line_height

            # Position
            if cfg["position"] == "center":
                y_base = (height - total_text_height) // 2
            else:
                y_base = height - total_text_height - 120

            # Find which word is currently being spoken (for highlight)
            current_word_idx = 0
            for wi, w in enumerate(chunk):
                w_start = w.get("start", 0)
                w_end = w.get("end", 0)
                if w_start <= t < w_end:
                    current_word_idx = wi
                    break
                if t >= w_end:
                    current_word_idx = wi

            # Render each line with word-level highlighting
            word_flat_idx = 0
            for line_idx, line in enumerate(lines):
                y = y_base + line_idx * line_height

                # Calculate x to center the line
                bbox = font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                x_start = (width - line_width) // 2

                # Render word by word for highlighting
                x_cursor = x_start
                line_words = line.split(" ")
                for lw_idx, lw in enumerate(line_words):
                    # Is this the currently highlighted word?
                    is_highlighted = (word_flat_idx == current_word_idx)
                    color = cfg["highlight_color"] if is_highlighted else cfg["color"]

                    _draw_outlined_text(
                        draw, (x_cursor, y), lw, font,
                        fill=color,
                        outline_color=cfg["outline_color"],
                        outline_width=cfg["outline_width"],
                    )

                    # Advance cursor
                    bbox = font.getbbox(lw + " ")
                    x_cursor += bbox[2] - bbox[0]
                    word_flat_idx += 1

        # Save frame
        frame_path = frames_dir / f"frame_{frame_idx:06d}.png"
        img.save(frame_path, "PNG")

    # Encode frames into a transparent video (VP9 with alpha)
    # Use mov+png for transparency since VP9 alpha is complex
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%06d.png"),
        "-c:v", "png",
        "-pix_fmt", "rgba",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Cleanup frames
    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)

    if result.returncode != 0:
        raise RuntimeError(f"Caption video encode failed: {result.stderr[-500:]}")

    return output_path


def burn_pillow_captions(
    video_path: Path,
    word_timestamps: list[dict],
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    style: str = "hormozi",
) -> Path:
    """Burn Pillow-rendered captions onto a video.

    This is a two-step process:
    1. Render caption overlay as transparent PNG video
    2. Composite onto main video with ffmpeg overlay filter
    """
    from ytauto.services.ffmpeg import get_audio_duration

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

    # Render caption overlay
    overlay_path = output_path.parent / "_caption_overlay.mov"
    render_caption_overlay(
        word_timestamps, duration, overlay_path,
        width=width, height=height, fps=fps, style=style,
    )

    # Composite: main video + caption overlay
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(overlay_path),
        "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1[outv]",
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Cleanup
    overlay_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"Caption compositing failed: {result.stderr[-500:]}")

    return output_path
