"""Caption generation — ASS subtitle format with animation effects.

Generates word-level timed captions using Whisper timestamps, with support
for multiple animation styles (pop, bounce, karaoke, highlight, etc.).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CaptionStyle:
    """Caption styling configuration."""
    name: str = "bold_centered"
    font_name: str = "Arial-Bold"
    font_size: int = 58
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#00D4FF"
    outline_color: str = "#000000"
    outline_width: int = 3
    shadow_depth: int = 2
    alignment: int = 5  # ASS alignment: 5 = center-middle, 2 = bottom-center
    margin_v: int = 50
    words_per_line: int = 3
    animation: str = "none"  # none, karaoke, pop, bounce, highlight, fade


# Pre-built style presets
CAPTION_PRESETS: dict[str, CaptionStyle] = {
    "bold_centered": CaptionStyle(),
    "subtitle_bottom": CaptionStyle(
        name="subtitle_bottom", font_name="Arial", font_size=42,
        outline_width=2, shadow_depth=1, alignment=2, margin_v=30,
        words_per_line=5, animation="none",
    ),
    "karaoke": CaptionStyle(
        name="karaoke", font_size=60, highlight_color="#FFD700",
        animation="karaoke", words_per_line=4,
    ),
    "highlight": CaptionStyle(
        name="highlight", font_size=62, highlight_color="#00D4FF",
        animation="highlight", words_per_line=3,
    ),
    "pop": CaptionStyle(
        name="pop", font_size=64, animation="pop", words_per_line=3,
    ),
    "bounce": CaptionStyle(
        name="bounce", font_size=60, animation="bounce", words_per_line=3,
    ),
    "hormozi": CaptionStyle(
        name="hormozi", font_name="Montserrat-ExtraBold", font_size=64,
        highlight_color="#FFD700", outline_width=4, shadow_depth=3,
        animation="pop", words_per_line=3,
    ),
    "mrbeast": CaptionStyle(
        name="mrbeast", font_name="Impact", font_size=68,
        highlight_color="#FF0000", outline_width=4, shadow_depth=2,
        animation="bounce", words_per_line=2,
    ),
    "cinematic": CaptionStyle(
        name="cinematic", font_name="Georgia", font_size=44,
        outline_width=2, shadow_depth=1, alignment=2, margin_v=40,
        words_per_line=6, animation="fade",
    ),
    "tiktok": CaptionStyle(
        name="tiktok", font_name="Montserrat-ExtraBold", font_size=72,
        outline_width=5, shadow_depth=3, animation="pop", words_per_line=2,
    ),
    "minimal": CaptionStyle(
        name="minimal", font_name="Helvetica", font_size=36,
        outline_width=1, shadow_depth=0, alignment=2, margin_v=25,
        words_per_line=6, animation="none",
    ),
}


def _color_to_ass(hex_color: str) -> str:
    """Convert #RRGGBB to ASS &HBBGGRR format."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _time_to_ass(seconds: float) -> str:
    """Convert seconds to ASS timestamp H:MM:SS.cc."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _chunk_words(words: list[dict], words_per_line: int) -> list[list[dict]]:
    """Group words into caption chunks."""
    chunks: list[list[dict]] = []
    current: list[dict] = []

    for w in words:
        current.append(w)
        text = w.get("word", w.get("text", ""))
        # Break at punctuation or word limit
        if len(current) >= words_per_line or text.rstrip().endswith((".", "!", "?", ",")):
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)
    return chunks


def generate_ass_captions(
    word_timestamps: list[dict],
    output_path: Path,
    style: CaptionStyle | str = "bold_centered",
    video_width: int = 1920,
    video_height: int = 1080,
) -> Path:
    """Generate an ASS subtitle file from word-level timestamps.

    Args:
        word_timestamps: List of dicts with 'word'/'text', 'start', 'end' keys.
        output_path: Path to write the .ass file.
        style: CaptionStyle instance or preset name string.
        video_width: Video width for scaling.
        video_height: Video height for scaling.
    """
    if isinstance(style, str):
        style = CAPTION_PRESETS.get(style, CAPTION_PRESETS["bold_centered"])

    primary = _color_to_ass(style.primary_color)
    outline = _color_to_ass(style.outline_color)
    highlight = _color_to_ass(style.highlight_color)
    bold = 1 if "bold" in style.font_name.lower() or "Bold" in style.font_name else 0

    # ASS header
    header = f"""[Script Info]
Title: ytauto Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_name},{style.font_size},{primary},&H000000FF,{outline},&H80000000,{bold},0,0,0,100,100,0,0,1,{style.outline_width},{style.shadow_depth},{style.alignment},40,40,{style.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    chunks = _chunk_words(word_timestamps, style.words_per_line)
    events: list[str] = []

    for chunk in chunks:
        if not chunk:
            continue

        start = chunk[0].get("start", 0)
        end = chunk[-1].get("end", start + 1)
        text_parts = [w.get("word", w.get("text", "")) for w in chunk]

        start_ts = _time_to_ass(start)
        end_ts = _time_to_ass(end)

        if style.animation == "karaoke":
            # Progressive fill with \kf tags
            karaoke_parts: list[str] = []
            for w in chunk:
                dur_cs = int((w.get("end", 0) - w.get("start", 0)) * 100)
                word_text = w.get("word", w.get("text", ""))
                karaoke_parts.append(f"{{\\kf{dur_cs}}}{word_text}")
            text = " ".join(karaoke_parts)
        elif style.animation == "highlight":
            # Word-by-word color highlight
            hl_parts: list[str] = []
            for i, w in enumerate(chunk):
                word_text = w.get("word", w.get("text", ""))
                # Highlight current word — simplified: highlight all in accent color
                hl_parts.append(f"{{\\c{highlight}}}{word_text}{{\\r}}" if i == 0 else word_text)
            text = " ".join(hl_parts)
        elif style.animation == "pop":
            # Scale pop-in
            text = "{\\fscx0\\fscy0\\t(0,150,\\fscx130\\fscy130)\\t(150,250,\\fscx100\\fscy100)}" + " ".join(text_parts)
        elif style.animation == "bounce":
            # Drop-in bounce
            text = "{\\fscx0\\fscy0\\t(0,100,\\fscx120\\fscy120)\\t(100,200,\\fscx100\\fscy100)}" + " ".join(text_parts)
        elif style.animation == "fade":
            # Simple fade-in/out
            text = "{\\fad(200,150)}" + " ".join(text_parts)
        else:
            text = " ".join(text_parts)

        events.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")

    ass_content = header + "\n".join(events) + "\n"
    output_path.write_text(ass_content, encoding="utf-8")
    return output_path


def burn_captions(
    video_path: Path,
    ass_path: Path,
    output_path: Path,
) -> Path:
    """Burn ASS captions into a video using ffmpeg's ass filter."""
    # Escape path for ffmpeg
    escaped = str(ass_path).replace("'", "'\\''").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"ass='{escaped}'",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Caption burn failed: {result.stderr[-500:]}")
    return output_path


def transcribe_for_timestamps(
    audio_path: Path,
    output_path: Path,
) -> list[dict]:
    """Transcribe audio to get word-level timestamps using Whisper via ffmpeg.

    Falls back to simple sentence-level timing if Whisper is unavailable.
    """
    # Try using openai whisper API
    try:
        import openai
        from ytauto.config.settings import get_settings
        settings = get_settings()
        if settings.has_openai():
            client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())
            with open(audio_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                )
            words = []
            for w in getattr(transcript, "words", []):
                words.append({
                    "word": w.word.strip(),
                    "start": w.start,
                    "end": w.end,
                })
            if words:
                import json
                output_path.write_text(json.dumps(words, indent=2), encoding="utf-8")
                return words
    except Exception:
        pass

    # Fallback: estimate timing from narration text
    return _estimate_word_timestamps(audio_path, output_path)


def _estimate_word_timestamps(audio_path: Path, output_path: Path) -> list[dict]:
    """Estimate word timestamps based on audio duration and word count."""
    from ytauto.services.ffmpeg import get_audio_duration

    duration = get_audio_duration(audio_path)

    # Read narration text if available
    narration_path = audio_path.parent / "narration.txt"
    if narration_path.exists():
        text = narration_path.read_text(encoding="utf-8")
    else:
        return []

    words_list = text.split()
    if not words_list:
        return []

    time_per_word = duration / len(words_list)
    timestamps: list[dict] = []

    for i, word in enumerate(words_list):
        timestamps.append({
            "word": word,
            "start": round(i * time_per_word, 3),
            "end": round((i + 1) * time_per_word, 3),
        })

    import json
    output_path.write_text(json.dumps(timestamps, indent=2), encoding="utf-8")
    return timestamps
