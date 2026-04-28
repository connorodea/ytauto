"""Bold text overlays — large motivational-style text burned onto video.

Creates the signature look of faceless motivation/business Shorts:
big bold text at the top or center of the frame, styled like
Infinite Wealth Lab, Motivation Madness, etc.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def burn_text_overlays(
    video_path: Path,
    text_segments: list[dict],
    output_path: Path,
    font_size: int = 58,
    font_color: str = "white",
    outline_color: str = "black",
    outline_width: int = 4,
    position: str = "top",
    bg_opacity: float = 0.0,
) -> Path:
    """Burn bold text overlays onto a video.

    Each segment in text_segments should have:
        - text: The phrase to display (will be auto-wrapped)
        - start: Start time in seconds
        - end: End time in seconds

    Args:
        position: "top" (20% from top), "center" (middle), "bottom" (80%)
        bg_opacity: Background box opacity (0 = no box, 0.5 = semi-transparent)
    """
    if not text_segments:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-c", "copy", str(output_path)],
            capture_output=True, check=True,
        )
        return output_path

    # Build drawtext filter chain
    drawtext_filters: list[str] = []

    for seg in text_segments:
        text = seg["text"]
        start = seg["start"]
        end = seg["end"]

        # Escape for ffmpeg drawtext
        safe_text = (
            text
            .replace("\\", "\\\\")
            .replace("'", "\u2019")  # Use smart quote to avoid escaping issues
            .replace(":", "\\:")
            .replace("%", "%%")
        )

        # Auto line-wrap: split into lines of ~20 chars for vertical video
        words = safe_text.split()
        lines: list[str] = []
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 > 22:
                lines.append(current_line)
                current_line = word
            else:
                current_line = f"{current_line} {word}".strip()
        if current_line:
            lines.append(current_line)

        # Make all text uppercase for that motivational look
        wrapped = "\\n".join(line.upper() for line in lines)

        # Position
        if position == "top":
            y_expr = "h*0.12"
        elif position == "center":
            y_expr = "(h-text_h)/2"
        else:
            y_expr = "h*0.75"

        # Fade in/out
        fade_in = 0.2
        fade_out = 0.2
        fade_in_end = start + fade_in
        fade_out_start = end - fade_out

        alpha_expr = (
            f"if(lt(t\\,{fade_in_end})\\,(t-{start})/{fade_in}\\,"
            f"if(gt(t\\,{fade_out_start})\\,({end}-t)/{fade_out}\\,1))"
        )

        # Build drawtext
        dt_parts = [
            f"drawtext=text='{wrapped}'",
            f"fontsize={font_size}",
            f"fontcolor={font_color}",
            f"borderw={outline_width}",
            f"bordercolor={outline_color}",
            f"x=(w-text_w)/2",
            f"y={y_expr}",
            f"enable='between(t,{start},{end})'",
            f"alpha='{alpha_expr}'",
        ]

        # Optional background box
        if bg_opacity > 0:
            dt_parts.extend([
                f"box=1",
                f"boxcolor=black@{bg_opacity}",
                f"boxborderw=16",
            ])

        drawtext_filters.append(":".join(dt_parts))

    vf = ",".join(drawtext_filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Text overlay failed: {result.stderr[-500:]}")

    return output_path


def extract_key_phrases(script: dict) -> list[dict]:
    """Extract the key text overlay phrases from a Shorts script.

    Returns a list of phrases timed to each section, designed to be
    shown as big bold text overlays on the video.
    """
    phrases: list[dict] = []

    # The hook is the first phrase
    hook = script.get("hook", "")
    if hook:
        # Take the first sentence or first ~8 words as the overlay text
        first_sentence = hook.split(".")[0].split("?")[0].split("!")[0]
        words = first_sentence.split()
        if len(words) > 10:
            first_sentence = " ".join(words[:8]) + "..."
        phrases.append({"text": first_sentence, "type": "hook"})

    # Each section heading or key phrase
    for section in script.get("sections", []):
        narration = section.get("narration", "")
        heading = section.get("heading", "")

        # Use heading if available, otherwise extract first impactful sentence
        if heading and len(heading) < 50:
            phrases.append({"text": heading, "type": "section"})
        elif narration:
            first = narration.split(".")[0].split("?")[0].split("!")[0]
            words = first.split()
            if len(words) > 8:
                first = " ".join(words[:7])
            phrases.append({"text": first, "type": "section"})

    # Outro CTA
    outro = script.get("outro", "")
    if outro:
        # Short CTA phrase
        words = outro.split()[:6]
        phrases.append({"text": " ".join(words), "type": "cta"})

    return phrases
