"""Shorts command — real footage + original audio + bold text overlays.

Replicates the Infinite Wealth Lab format:
- Real movie/TV clips (Suits, etc.) with ORIGINAL AUDIO kept
- Center-cropped to vertical 9:16
- Bold motivational text overlays burned on top
- No AI voiceover — the show's dialogue IS the content
"""

from __future__ import annotations

import json
import random
import subprocess
import shutil
import time
from pathlib import Path

import typer
from rich.live import Live
from rich.table import Table

from ytauto.cli.theme import (
    ACCENT,
    ACCENT_DIM,
    SUCCESS,
    ERROR,
    console,
    error,
    header,
    result_panel,
    success,
    warning,
)
from ytauto.config.settings import get_settings
from ytauto.models.job import Job, PipelineStep
from ytauto.store.json_store import JsonDirectoryStore

SHORTS_STAGES = [
    "text_generation",
    "select_clips",
    "crop_and_assemble",
    "burn_text",
    "done",
]

STAGE_LABELS = {
    "text_generation": ("Writing text", "Generating bold overlay phrases..."),
    "select_clips": ("Selecting clips", "Picking clips from your library..."),
    "crop_and_assemble": ("Cropping 9:16", "Vertical crop + concat with original audio..."),
    "burn_text": ("Burning text", "Rendering bold text overlays with Pillow..."),
    "done": ("Finishing", ""),
}


def _build_stage_table(
    stages: list[str], completed: set[str], current: str | None,
    failed: str | None, timings: dict[str, float],
) -> Table:
    table = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
    table.add_column("icon", width=3)
    table.add_column("stage", min_width=30)
    table.add_column("time", width=8, justify="right")

    for name in stages:
        label, detail = STAGE_LABELS.get(name, (name, ""))
        if name in completed:
            icon = f"[bold {SUCCESS}]\u2713[/bold {SUCCESS}]"
            t = f"[dim]{timings.get(name, 0):.1f}s[/dim]"
            text = f"[dim]{label}[/dim]"
        elif name == failed:
            icon = f"[bold {ERROR}]\u2717[/bold {ERROR}]"
            t = ""
            text = f"[bold {ERROR}]{label}[/bold {ERROR}]"
        elif name == current:
            icon = f"[bold {ACCENT}]\u25b8[/bold {ACCENT}]"
            t = f"[{ACCENT}]...[/{ACCENT}]"
            text = f"[bold bright_white]{label}[/bold bright_white]  [{ACCENT_DIM}]{detail}[/{ACCENT_DIM}]"
        else:
            icon = "[dim]\u2022[/dim]"
            t = ""
            text = f"[dim]{label}[/dim]"
        table.add_row(icon, text, t)
    return table


def shorts(
    topic: str = typer.Argument(None, help="The Shorts topic — generates text overlays to match."),
    seconds: int = typer.Option(
        45, "--seconds", "-s",
        help="Target duration in seconds (30-60).",
    ),
    engine: str = typer.Option(
        None, "--engine", "-e",
        help="LLM engine for text generation: claude or openai.",
    ),
    clips_source: str = typer.Option(
        "library", "--clips",
        help="Clip source: 'library' (your clips), or path to a folder.",
    ),
    clip_tag: str = typer.Option(
        None, "--clip-tag",
        help="Filter library clips by tag (e.g., 'suits', 'business').",
    ),
    captions_style: str = typer.Option(
        "hormozi", "--captions", "-c",
        help="Caption style: hormozi, mrbeast, tiktok, cinematic, minimal.",
    ),
    num_clips: int = typer.Option(
        4, "--num-clips", "-n",
        help="Number of clips to use (3-8).",
    ),
    open_after: bool = typer.Option(
        False, "--open",
        help="Open the Short after creation.",
    ),
) -> None:
    """Create a YouTube Short with real footage, original audio, and bold text.

    Uses clips from your library (Suits, Peaky Blinders, etc.) with the
    ORIGINAL show audio playing. Adds bold motivational text overlays on top.
    No AI voiceover — the show's dialogue IS the content.

    Like Infinite Wealth Lab, Motivation Madness, etc.
    """
    settings = get_settings()
    settings.ensure_directories()

    engine = engine or settings.default_llm_provider
    seconds = max(30, min(60, seconds))
    num_clips = max(2, min(8, num_clips))

    # Interactive topic prompt
    if not topic:
        console.print()
        console.print(header("New YouTube Short", "What text should appear on screen?"))
        console.print()
        topic = typer.prompt("  Topic / theme for text overlays")
        if not topic.strip():
            error("Topic cannot be empty.")
            raise typer.Exit(1)
        console.print()

    # Determine source label
    if clips_source == "library":
        source_label = "Clip Library"
        if clip_tag:
            source_label += f" (tag: {clip_tag})"
    else:
        source_label = f"Folder: {clips_source}"

    # Create job
    job = Job(topic=topic, duration_config=f"{seconds}s", engine_config=engine)
    work_dir = settings.workspaces_dir / job.id
    work_dir.mkdir(parents=True, exist_ok=True)
    job.workspace_dir = str(work_dir)
    job.steps = [PipelineStep(name=name) for name in SHORTS_STAGES]

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    job_store.save(job)

    console.print()
    console.print(header(
        "Creating YouTube Short",
        f'"{topic}"\n'
        f"Duration: ~{seconds}s  \u2502  Clips: {source_label}  \u2502  Text style: {captions_style}\n"
        f"Original audio: \u2713  \u2502  AI voiceover: none  \u2502  Job: {job.id}",
    ))
    console.print()

    completed: set[str] = set()
    timings: dict[str, float] = {}
    current_stage: str | None = None
    text_phrases: list[str] = []
    clip_paths: list[Path] = []
    final_path: Path | None = None
    title_text = topic

    try:
        with Live(
            _build_stage_table(SHORTS_STAGES, completed, None, None, timings),
            console=console, refresh_per_second=4,
        ) as live:

            def _run(name: str, fn):
                nonlocal current_stage
                current_stage = name
                live.update(_build_stage_table(SHORTS_STAGES, completed, current_stage, None, timings))
                t0 = time.monotonic()
                fn()
                elapsed = time.monotonic() - t0
                completed.add(name)
                timings[name] = elapsed
                live.update(_build_stage_table(SHORTS_STAGES, completed, None, None, timings))

            # ── 1. Generate bold text overlay phrases ────────────────────
            def do_text_gen():
                nonlocal text_phrases, title_text
                text_phrases = _generate_overlay_text(
                    topic, num_clips, engine, settings,
                )
                if text_phrases:
                    title_text = text_phrases[0]
                (work_dir / "text_overlays.json").write_text(
                    json.dumps(text_phrases, indent=2), encoding="utf-8",
                )

            _run("text_generation", do_text_gen)

            # ── 2. Select clips from library ─────────────────────────────
            def do_select():
                nonlocal clip_paths
                if clips_source == "library":
                    from ytauto.services.clips import select_clips_for_sections
                    dummy_sections = [{"narration": ""} for _ in range(num_clips)]
                    clip_paths = select_clips_for_sections(dummy_sections, tag=clip_tag)
                else:
                    folder = Path(clips_source).expanduser().resolve()
                    if not folder.is_dir():
                        raise RuntimeError(f"Folder not found: {clips_source}")
                    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
                    all_vids = [f for f in folder.iterdir() if f.suffix.lower() in video_exts]
                    if not all_vids:
                        raise RuntimeError(f"No videos in {clips_source}")
                    random.shuffle(all_vids)
                    clip_paths = [all_vids[i % len(all_vids)] for i in range(num_clips)]

            _run("select_clips", do_select)

            # ── 3. Crop to 9:16 + concat WITH ORIGINAL AUDIO ────────────
            def do_crop():
                nonlocal final_path
                from ytauto.video.crop import crop_to_vertical, get_video_duration

                if not clip_paths:
                    raise RuntimeError("No clips selected.")

                target_per_clip = seconds / len(clip_paths)

                cropped: list[Path] = []
                for i, clip in enumerate(clip_paths):
                    out = work_dir / f"_cropped_{i:03d}.mp4"
                    clip_dur = get_video_duration(clip)
                    trim_dur = min(target_per_clip, clip_dur)
                    # Crop to vertical but KEEP AUDIO
                    _crop_with_audio(clip, out, trim_dur)
                    cropped.append(out)

                # Concat all clips with audio
                concat_file = work_dir / "_concat.txt"
                concat_file.write_text(
                    "\n".join(f"file '{p}'" for p in cropped), encoding="utf-8",
                )

                joined = work_dir / "_joined.mp4"
                subprocess.run([
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_file),
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k",
                    str(joined),
                ], capture_output=True, check=True)

                final_path = joined

                for f in cropped:
                    f.unlink(missing_ok=True)
                concat_file.unlink(missing_ok=True)

            _run("crop_and_assemble", do_crop)

            # ── 4. Burn bold text overlays using Pillow ──────────────────
            def do_burn():
                nonlocal final_path
                if not text_phrases or not final_path:
                    return

                from ytauto.video.pillow_captions import burn_pillow_captions

                # Convert text phrases into word timestamps format
                # Each phrase gets shown for one clip's duration
                dur = _get_duration(final_path)
                phrase_dur = dur / len(text_phrases)

                word_ts: list[dict] = []
                for i, phrase in enumerate(text_phrases):
                    start = i * phrase_dur
                    words = phrase.split()
                    word_dur = phrase_dur / max(len(words), 1)
                    for j, word in enumerate(words):
                        word_ts.append({
                            "word": word,
                            "start": start + j * word_dur,
                            "end": start + (j + 1) * word_dur,
                        })

                output = work_dir / "_with_text.mp4"
                burn_pillow_captions(
                    video_path=final_path,
                    word_timestamps=word_ts,
                    output_path=output,
                    width=1080, height=1920, fps=30,
                    style=captions_style,
                )

                final_path.unlink(missing_ok=True)
                final_path = output

            _run("burn_text", do_burn)

            # ── 5. Finalize ──────────────────────────────────────────────
            def do_done():
                nonlocal final_path
                title_slug = topic.replace(" ", "_")[:40]
                dest = work_dir / f"{title_slug}_short.mp4"
                if final_path and final_path.exists() and final_path != dest:
                    shutil.move(str(final_path), str(dest))
                    final_path = dest

                job.video_path = str(final_path) if final_path else ""
                job.status = "completed"
                job.touch()
                job_store.save(job)

            _run("done", do_done)

    except Exception as exc:
        console.print(_build_stage_table(SHORTS_STAGES, completed, None, current_stage, timings))
        console.print()
        error(f"Shorts pipeline failed: {exc}")
        console.print(f"\n  [dim]Job ID: {job.id}[/dim]\n")
        raise typer.Exit(1)

    # Result panel
    rows: list[tuple[str, str]] = [
        ("Job ID", f"[id]{job.id}[/id]"),
        ("Title", f"[bold bright_white]{title_text}[/bold bright_white]"),
        ("Format", "9:16 Vertical (1080x1920)"),
        ("Audio", "Original show audio (no AI voiceover)"),
        ("Source", source_label),
    ]

    if final_path and final_path.exists():
        size_mb = final_path.stat().st_size / (1024 * 1024)
        rows.append(("Video", f"[path]{final_path}[/path]"))
        rows.append(("Size", f"{size_mb:.1f} MB"))
        dur = _get_duration(final_path)
        rows.append(("Duration", f"{int(dur)}s"))

    rows.append(("Clips", f"{len(clip_paths)}"))
    rows.append(("Text Style", captions_style))
    rows.append(("Total Time", f"{sum(timings.values()):.0f}s"))

    console.print()
    console.print(result_panel("Short Created", rows))
    console.print()
    success("Your YouTube Short is ready!")
    console.print(f"  [dim]View:[/dim]   [accent]ytauto job {job.id}[/accent]")
    console.print(f"  [dim]Open:[/dim]   [accent]ytauto open {job.id}[/accent]")
    console.print(f"  [dim]Upload:[/dim] [accent]ytauto upload {job.id}[/accent]\n")

    if open_after and final_path and final_path.exists():
        import platform
        if platform.system() == "Darwin":
            subprocess.Popen(["open", str(final_path)])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_overlay_text(
    topic: str,
    num_phrases: int,
    engine: str,
    settings,
) -> list[str]:
    """Generate bold text overlay phrases using AI."""
    from ytauto.services.retry import retry
    import anthropic
    import openai

    prompt = (
        f"Generate exactly {num_phrases} bold motivational text overlay phrases "
        f"for a YouTube Short about: {topic}\n\n"
        f"Each phrase should be 3-7 words, punchy, uppercase-worthy, "
        f"like what you'd see on Infinite Wealth Lab or motivation channels.\n\n"
        f"Return ONLY a JSON array of strings, nothing else. Example:\n"
        f'["WINNERS NEVER QUIT", "OUTWORK EVERYONE", "NO EXCUSES"]'
    )

    try:
        if engine == "claude" and settings.has_anthropic():
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
        elif settings.has_openai():
            client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())
            resp = client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt + "\nReturn as {\"phrases\": [...]}"}],
                max_tokens=512,
            )
            raw = resp.choices[0].message.content.strip()
        else:
            # Fallback: generate from topic
            words = topic.upper().split()
            return [" ".join(words[i:i+4]) for i in range(0, len(words), 4)][:num_phrases]

        # Parse JSON
        import re
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(p) for p in data][:num_phrases]
            if isinstance(data, dict) and "phrases" in data:
                return [str(p) for p in data["phrases"]][:num_phrases]
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                return [str(p) for p in json.loads(match.group())][:num_phrases]

    except Exception as exc:
        logger_msg = f"Text generation failed: {exc}"

    # Fallback
    return [topic.upper()]


def _crop_with_audio(
    input_path: Path,
    output_path: Path,
    duration: float,
    target_width: int = 1080,
    target_height: int = 1920,
) -> Path:
    """Center-crop a video to 9:16 vertical, keeping the audio track."""
    # Get input dimensions
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            str(input_path),
        ],
        capture_output=True, text=True, check=True,
    )
    parts = probe.stdout.strip().split(",")
    in_w, in_h = int(parts[0]), int(parts[1])

    target_aspect = target_width / target_height
    crop_w = int(in_h * target_aspect)
    crop_h = in_h
    crop_x = max(0, (in_w - crop_w) // 2)

    if crop_w > in_w:
        crop_w = in_w
        crop_h = int(in_w / target_aspect)
        crop_x = 0

    vf = (
        f"crop={crop_w}:{crop_h}:{crop_x}:0,"
        f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
        f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Crop failed: {result.stderr[-500:]}")
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
