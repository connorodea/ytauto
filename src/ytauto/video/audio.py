"""Audio processing — mixing, normalization, sound effects."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

# Keyword → SFX type mapping
SFX_KEYWORDS: dict[str, str] = {
    "money": "cash", "dollar": "cash", "million": "cash", "billion": "cash",
    "profit": "cash", "revenue": "cash", "wealth": "cash",
    "but": "transition", "however": "transition", "yet": "transition",
    "actually": "transition", "meanwhile": "transition",
    "secret": "reveal", "truth": "reveal", "hidden": "reveal",
    "shocking": "reveal", "exposed": "reveal", "revealed": "reveal",
    "first": "pop", "second": "pop", "third": "pop", "next": "pop",
    "number": "pop", "step": "pop",
    "important": "emphasis", "key": "emphasis", "critical": "emphasis",
    "remember": "emphasis", "listen": "emphasis",
    "success": "success", "win": "success", "winner": "success",
    "fail": "fail", "mistake": "fail", "wrong": "fail", "error": "fail",
}


def mix_voiceover_and_music(
    voiceover_path: Path,
    music_path: Path,
    output_path: Path,
    music_volume: float = 0.15,
    music_fade_in: float = 1.0,
    music_fade_out: float = 2.0,
) -> Path:
    """Mix voiceover with background music, applying volume ducking and fades.

    The music is looped to match voiceover duration, attenuated, and faded.
    """
    vo_duration = _get_duration(voiceover_path)
    music_duration = _get_duration(music_path)

    # Calculate loop count needed
    loop_count = max(0, int(vo_duration / music_duration))

    fade_out_start = max(0.0, vo_duration - music_fade_out)

    filter_complex = (
        f"[0:a]volume=1.0[vo];"
        f"[1:a]atrim=duration={vo_duration:.2f},asetpts=PTS-STARTPTS,"
        f"volume={music_volume},"
        f"afade=type=in:start_time=0:duration={music_fade_in},"
        f"afade=type=out:start_time={fade_out_start:.2f}:duration={music_fade_out}[music];"
        f"[vo][music]amix=inputs=2:duration=first:dropout_transition=0[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(voiceover_path),
        "-stream_loop", str(loop_count),
        "-i", str(music_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio mixing failed: {result.stderr[-500:]}")
    return output_path


def normalize_audio(
    audio_path: Path,
    output_path: Path,
    target_lufs: float = -16.0,
) -> Path:
    """Normalize audio to EBU R128 loudness standard.

    Default target: -16.0 LUFS (streaming standard).
    """
    af = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=summary"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-af", af,
        "-ar", "44100",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio normalization failed: {result.stderr[-500:]}")
    return output_path


def detect_sfx_points(
    narration_text: str,
    max_sfx: int = 12,
) -> list[dict]:
    """Detect keyword-based sound effect insertion points from narration text.

    Returns list of dicts with: word, sfx_type, char_offset.
    """
    points: list[dict] = []
    words = narration_text.lower().split()
    char_offset = 0

    for word in words:
        clean = word.strip(".,!?;:'\"()[]")
        if clean in SFX_KEYWORDS and len(points) < max_sfx:
            # Deduplicate: skip if same SFX type within last 3 entries
            sfx_type = SFX_KEYWORDS[clean]
            recent_types = [p["sfx_type"] for p in points[-3:]]
            if sfx_type not in recent_types:
                points.append({
                    "word": clean,
                    "sfx_type": sfx_type,
                    "char_offset": char_offset,
                })
        char_offset += len(word) + 1

    return points


def mix_sfx(
    audio_path: Path,
    sfx_entries: list[dict],
    output_path: Path,
) -> Path:
    """Mix sound effect files into an audio track at specified timestamps.

    Each entry in sfx_entries must have: sfx_path (Path), start_time (float), volume (float).
    """
    if not sfx_entries:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio_path), "-c", "copy", str(output_path)],
            capture_output=True, check=True,
        )
        return output_path

    inputs = ["-i", str(audio_path)]
    filter_parts: list[str] = []

    for i, entry in enumerate(sfx_entries):
        inputs.extend(["-i", str(entry["sfx_path"])])
        delay_ms = int(entry["start_time"] * 1000)
        vol = entry.get("volume", 0.5)
        filter_parts.append(
            f"[{i + 1}:a]adelay={delay_ms}|{delay_ms},volume={vol}[sfx{i}]"
        )

    # Mix all streams
    all_labels = "[0:a]" + "".join(f"[sfx{i}]" for i in range(len(sfx_entries)))
    n = len(sfx_entries) + 1
    filter_parts.append(f"{all_labels}amix=inputs={n}:duration=first:dropout_transition=2[out]")

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"SFX mixing failed: {result.stderr[-500:]}")
    return output_path


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
