"""Shorts compositor — builds the full IWL-style composite frame.

Creates the Infinite Wealth Lab format:
- Black 1080x1920 canvas
- Title with colored keywords at top
- Landscape clip centered (not cropped) in middle
- Sentence-level subtitles at bottom of video area
- Original audio preserved
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

W, H = 1080, 1920
FPS = 30
VIDEO_WIDTH = 1080           # Clip fills full width — edge to edge
VIDEO_Y = 340                # Top of video area (right below title)
TITLE_Y = 60                 # Y position for title text start
SUBTITLE_MARGIN = 70         # px above bottom of video area

# Colors for highlighted title words
HIGHLIGHT_COLORS = [
    (0, 220, 80),    # green
    (255, 215, 0),   # gold/yellow
    (220, 50, 50),   # red
    (0, 180, 255),   # blue
]


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFCompact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default(size=size)


def _draw_outlined(draw, xy, text, font, fill, outline=(0, 0, 0), ow=2):
    x, y = xy
    for dx in range(-ow, ow + 1):
        for dy in range(-ow, ow + 1):
            if dx * dx + dy * dy <= ow * ow:
                draw.text((x + dx, y + dy), text, font=font, fill=(*outline, 255))
    draw.text((x, y), text, font=font, fill=(*fill, 255))


def _chunk_subtitle(words: list[dict], max_words: int = 8) -> list[tuple[float, float, str]]:
    """Group word timestamps into sentence-level subtitle chunks."""
    chunks = []
    current_words = []
    for w in words:
        current_words.append(w)
        text = w.get("word", "")
        if len(current_words) >= max_words or text.rstrip().endswith((".", "!", "?", ",")):
            start = current_words[0]["start"]
            end = current_words[-1]["end"]
            phrase = " ".join(ww.get("word", "") for ww in current_words)
            chunks.append((start, end, phrase))
            current_words = []
    if current_words:
        start = current_words[0]["start"]
        end = current_words[-1]["end"]
        phrase = " ".join(ww.get("word", "") for ww in current_words)
        chunks.append((start, end, phrase))
    return chunks


def compose_short(
    clip_paths: list[Path],
    title: str,
    word_timestamps: list[dict],
    output_path: Path,
    highlight_words: list[str] | None = None,
    target_seconds: int = 50,
) -> Path:
    """Build the full IWL-style composite Short.

    1. Extract frames from source clips
    2. For each frame: draw black canvas + title + scaled clip + subtitle
    3. Encode frames + concatenated audio into final MP4
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work = output_path.parent / "_compose_work"
    work.mkdir(exist_ok=True)

    title_font = _get_font(52)
    sub_font = _get_font(38)

    # Pre-compute subtitle chunks
    sub_chunks = _chunk_subtitle(word_timestamps)

    # Determine clip durations
    clip_durations = []
    total_available = 0
    for cp in clip_paths:
        d = _get_dur(cp)
        clip_durations.append(d)
        total_available += d

    target_per_clip = target_seconds / len(clip_paths)

    # Pre-render the static title image (same for every frame)
    title_img = _render_title(title, highlight_words, title_font)

    # Process clips one at a time — extract frames, composite, save
    frames_dir = work / "frames"
    frames_dir.mkdir(exist_ok=True)
    audio_parts: list[Path] = []
    frame_count = 0

    for clip_idx, clip_path in enumerate(clip_paths):
        clip_dur = min(target_per_clip, clip_durations[clip_idx])
        clip_frames = int(clip_dur * FPS)
        time_offset = sum(min(target_per_clip, clip_durations[j]) for j in range(clip_idx))

        # Extract clip frames
        clip_frames_dir = work / f"clip_{clip_idx}"
        clip_frames_dir.mkdir(exist_ok=True)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(clip_path),
            "-t", str(clip_dur),
            "-vf", f"fps={FPS},scale={VIDEO_WIDTH}:-1",
            "-q:v", "3",
            str(clip_frames_dir / "f_%06d.jpg"),
        ], capture_output=True)

        # Extract audio segment
        audio_seg = work / f"audio_{clip_idx}.aac"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(clip_path),
            "-t", str(clip_dur),
            "-vn", "-c:a", "aac", "-b:a", "192k",
            str(audio_seg),
        ], capture_output=True)
        if audio_seg.exists():
            audio_parts.append(audio_seg)

        # Get actual extracted frame count
        extracted = sorted(clip_frames_dir.glob("f_*.jpg"))
        actual_frames = len(extracted)

        # Composite each frame
        for fi, frame_file in enumerate(extracted):
            t = time_offset + fi / FPS

            # Black canvas
            canvas = Image.new("RGB", (W, H), (0, 0, 0))

            # Paste title (static)
            canvas.paste(title_img, (0, 0), title_img)

            # Paste video frame — fill from title bottom to canvas bottom
            try:
                vframe = Image.open(frame_file)
                vw, vh = vframe.size

                # Fill the entire space below the title
                available_h = H - VIDEO_Y
                # Scale to fill width, then crop height to fit available space
                scale = W / vw
                target_vw = W
                target_vh = int(vh * scale)

                if target_vh < available_h:
                    # Video is shorter than available — scale to fill height instead
                    scale = available_h / vh
                    target_vw = int(vw * scale)
                    target_vh = available_h

                vframe = vframe.resize((target_vw, target_vh), Image.LANCZOS)

                # Center crop to W x available_h
                crop_x = max(0, (target_vw - W) // 2)
                crop_y = max(0, (target_vh - available_h) // 2)
                vframe = vframe.crop((crop_x, crop_y, crop_x + W, crop_y + available_h))
                canvas.paste(vframe, (0, VIDEO_Y))
                vw, vh = W, available_h

                # Draw subtitle near bottom of frame
                active_sub = _get_active_subtitle(sub_chunks, t)
                if active_sub:
                    draw = ImageDraw.Draw(canvas)
                    sub_y = H - 120  # ~120px from bottom of canvas
                    _draw_subtitle(draw, active_sub, sub_font, sub_y)

                vframe.close()
            except Exception:
                pass

            # Save composited frame
            out_frame = frames_dir / f"frame_{frame_count:06d}.jpg"
            canvas.save(out_frame, "JPEG", quality=90)
            canvas.close()
            frame_count += 1

        # Cleanup clip frames
        shutil.rmtree(clip_frames_dir, ignore_errors=True)

    # Concat audio segments
    audio_out = work / "audio_full.aac"
    if audio_parts:
        audio_list = work / "audio_list.txt"
        audio_list.write_text(
            "\n".join(f"file '{p}'" for p in audio_parts), encoding="utf-8",
        )
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(audio_list), "-c:a", "aac", "-b:a", "192k",
            str(audio_out),
        ], capture_output=True)

    # Encode final video from frames + audio
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%06d.jpg"),
    ]
    if audio_out.exists():
        cmd.extend(["-i", str(audio_out)])
        cmd.extend(["-map", "0:v", "-map", "1:a"])
    cmd.extend([
        "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path),
    ])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Final encode failed: {r.stderr[-500:]}")

    # Cleanup
    shutil.rmtree(work, ignore_errors=True)

    return output_path


def _render_title(
    title: str,
    highlight_words: list[str] | None,
    font: ImageFont.FreeTypeFont,
) -> Image.Image:
    """Render the static title overlay with colored keywords."""
    img = Image.new("RGBA", (W, VIDEO_Y), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    highlight_words = highlight_words or []
    # Build color map for highlighted words
    color_map: dict[str, tuple] = {}
    for i, hw in enumerate(highlight_words):
        color_map[hw.lower()] = HIGHLIGHT_COLORS[i % len(HIGHLIGHT_COLORS)]

    # Word-wrap title to fit width
    words = title.split()
    lines: list[list[str]] = []
    current_line: list[str] = []
    for word in words:
        test = " ".join(current_line + [word])
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > W - 80 and current_line:
            lines.append(current_line)
            current_line = [word]
        else:
            current_line.append(word)
    if current_line:
        lines.append(current_line)

    line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1] + 12
    total_height = len(lines) * line_height
    y_start = TITLE_Y + (VIDEO_Y - TITLE_Y - total_height) // 2

    for line_idx, line_words in enumerate(lines):
        # Calculate total line width for centering
        line_text = " ".join(line_words)
        bbox = font.getbbox(line_text)
        line_w = bbox[2] - bbox[0]
        x = (W - line_w) // 2
        y = y_start + line_idx * line_height

        # Draw word by word for coloring
        for word in line_words:
            clean = word.strip(".,!?:;'\"()[]💡🔥👑💼🤯❤️💔💸🚪")
            color = color_map.get(clean.lower(), (255, 255, 255))
            _draw_outlined(draw, (x, y), word, font, fill=color, outline=(0, 0, 0), ow=2)
            bbox = font.getbbox(word + " ")
            x += bbox[2] - bbox[0]

    return img


def _get_active_subtitle(
    chunks: list[tuple[float, float, str]], t: float,
) -> str | None:
    for start, end, text in chunks:
        if start <= t < end:
            return text
    return None


def _draw_subtitle(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, y: int):
    """Draw subtitle text centered at y position — bold, outlined, readable."""
    words = text.split()
    lines = []
    current = ""
    for w in words:
        test = f"{current} {w}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > W - 100 and current:
            lines.append(current)
            current = w
        else:
            current = test
    if current:
        lines.append(current)

    line_h = font.getbbox("Ay")[3] - font.getbbox("Ay")[1] + 12
    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2
        ly = y - (len(lines) - i) * line_h
        # Thick outline for readability over video
        _draw_outlined(draw, (x, ly), line, font, fill=(255, 255, 255), outline=(0, 0, 0), ow=4)


def _get_dur(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())
