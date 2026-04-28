"""Shorts command — create viral YouTube Shorts using stock footage + bold text overlays.

Replicates the style of channels like Infinite Wealth Lab:
- Real cinematic stock video clips (Pexels)
- Center-cropped to vertical 9:16
- Bold motivational text overlays
- Punchy voiceover narration
- Fast cuts between clips
"""

from __future__ import annotations

import json
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
    "script",
    "voiceover",
    "stock_footage",
    "crop_and_cut",
    "text_overlays",
    "done",
]

STAGE_LABELS = {
    "script": ("Writing hook", "Generating viral Shorts script..."),
    "voiceover": ("Recording voice", "Deepgram Aura TTS narration..."),
    "stock_footage": ("Sourcing footage", "Downloading cinematic stock clips from Pexels..."),
    "crop_and_cut": ("Cropping & cutting", "Vertical 9:16 crop + fast cuts + voiceover..."),
    "text_overlays": ("Adding text", "Burning bold text overlays..."),
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
    topic: str = typer.Argument(None, help="The Shorts topic or hook idea."),
    seconds: int = typer.Option(
        45, "--seconds", "-s",
        help="Target duration in seconds (30-60).",
    ),
    voice: str = typer.Option(
        None, "--voice", "-v",
        help="Deepgram Aura voice model.",
    ),
    engine: str = typer.Option(
        None, "--engine", "-e",
        help="LLM engine: claude or openai.",
    ),
    text_position: str = typer.Option(
        "top", "--text-pos",
        help="Text overlay position: top, center, bottom.",
    ),
    open_after: bool = typer.Option(
        False, "--open",
        help="Open the Short after creation.",
    ),
) -> None:
    """Create a viral YouTube Short with stock footage + bold text overlays.

    Uses real cinematic stock video (Pexels), cropped to 9:16 vertical,
    with bold motivational text burned on top — like Infinite Wealth Lab.
    """
    settings = get_settings()
    settings.ensure_directories()

    voice = voice or settings.default_tts_voice
    engine = engine or settings.default_llm_provider
    seconds = max(30, min(60, seconds))

    if not settings.has_pexels():
        error("Pexels API key required for stock footage Shorts.")
        console.print("  [dim]Set YTAUTO_PEXELS_API_KEY in ~/.ytauto/.env[/dim]")
        console.print("  [dim]Get a free key at: https://www.pexels.com/api/[/dim]\n")
        raise typer.Exit(1)

    # Interactive topic prompt
    if not topic:
        console.print()
        console.print(header("New YouTube Short", "What's the hook?"))
        console.print()
        topic = typer.prompt("  Topic / hook idea")
        if not topic.strip():
            error("Topic cannot be empty.")
            raise typer.Exit(1)
        console.print()

    # Create job
    job = Job(topic=topic, duration_config=f"{seconds}s", voice_config=voice, engine_config=engine)
    work_dir = settings.workspaces_dir / job.id
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "clips").mkdir(exist_ok=True)
    job.workspace_dir = str(work_dir)
    job.steps = [PipelineStep(name=name) for name in SHORTS_STAGES]

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    job_store.save(job)

    console.print()
    console.print(header(
        "Creating YouTube Short",
        f'"{topic}"\n'
        f"Duration: {seconds}s  \u2502  Voice: {voice}  \u2502  Text: {text_position}  \u2502  Stock footage: Pexels\n"
        f"Job: {job.id}",
    ))
    console.print()

    completed: set[str] = set()
    timings: dict[str, float] = {}
    current_stage: str | None = None
    script_data: dict = {}
    voiceover_path = work_dir / "voiceover.mp3"
    clip_paths: list[Path] = []
    final_path: Path | None = None

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

            # ── 1. Script ────────────────────────────────────────────────
            def do_script():
                nonlocal script_data
                from ytauto.services.shorts import generate_shorts_script
                script_data = generate_shorts_script(
                    topic=topic, target_seconds=seconds,
                    engine=engine, settings=settings,
                )
                (work_dir / "script.json").write_text(
                    json.dumps(script_data, indent=2), encoding="utf-8",
                )
                parts = [script_data.get("hook", "")]
                for s in script_data.get("sections", []):
                    parts.append(s.get("narration", ""))
                parts.append(script_data.get("outro", ""))
                narration = "\n\n".join(p for p in parts if p)
                (work_dir / "narration.txt").write_text(narration, encoding="utf-8")

            _run("script", do_script)

            # ── 2. Voiceover ─────────────────────────────────────────────
            def do_voiceover():
                from ytauto.services.tts import synthesize_voiceover
                narration = (work_dir / "narration.txt").read_text(encoding="utf-8")
                synthesize_voiceover(narration, voiceover_path, voice=voice, settings=settings)

            _run("voiceover", do_voiceover)

            # ── 3. Stock footage ─────────────────────────────────────────
            def do_stock():
                nonlocal clip_paths
                from ytauto.services.stockvideo import source_clips_for_shorts
                sections = script_data.get("sections", [])
                clip_paths = source_clips_for_shorts(
                    sections=sections,
                    output_dir=work_dir / "clips",
                    settings=settings,
                )

            _run("stock_footage", do_stock)

            # ── 4. Crop to vertical + assemble with voiceover ────────────
            def do_crop():
                nonlocal final_path
                import subprocess
                from ytauto.video.crop import crop_to_vertical, get_video_duration
                from ytauto.services.ffmpeg import get_audio_duration

                if not clip_paths:
                    raise RuntimeError("No stock footage clips downloaded.")

                audio_dur = get_audio_duration(voiceover_path)
                n_clips = len(clip_paths)
                target_per_clip = audio_dur / n_clips

                # Crop each clip to vertical and trim to target duration
                cropped: list[Path] = []
                for i, clip in enumerate(clip_paths):
                    out = work_dir / f"_cropped_{i:03d}.mp4"
                    clip_dur = get_video_duration(clip)
                    trim_dur = min(target_per_clip, clip_dur)
                    crop_to_vertical(clip, out, duration=trim_dur)
                    cropped.append(out)

                # Concatenate clips
                import tempfile
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
                    "-pix_fmt", "yuv420p", "-an",
                    str(joined),
                ], capture_output=True, check=True)

                # Mux with voiceover
                muxed = work_dir / "_muxed.mp4"
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", str(joined), "-i", str(voiceover_path),
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    str(muxed),
                ], capture_output=True, check=True)

                final_path = muxed

                # Cleanup
                for f in cropped:
                    f.unlink(missing_ok=True)
                concat_file.unlink(missing_ok=True)
                joined.unlink(missing_ok=True)

            _run("crop_and_cut", do_crop)

            # ── 5. Bold text overlays ────────────────────────────────────
            def do_text():
                nonlocal final_path
                from ytauto.services.ffmpeg import _has_filter, get_audio_duration

                if not _has_filter("drawtext"):
                    # Save text data but skip burn
                    from ytauto.video.text_overlay import extract_key_phrases
                    phrases = extract_key_phrases(script_data)
                    (work_dir / "text_overlays.json").write_text(
                        json.dumps(phrases, indent=2), encoding="utf-8",
                    )
                    return

                from ytauto.video.text_overlay import extract_key_phrases, burn_text_overlays

                phrases = extract_key_phrases(script_data)
                (work_dir / "text_overlays.json").write_text(
                    json.dumps(phrases, indent=2), encoding="utf-8",
                )

                if not phrases or not final_path:
                    return

                # Time the phrases evenly across the video
                audio_dur = get_audio_duration(voiceover_path)
                segment_dur = audio_dur / len(phrases)

                text_segments = []
                for i, phrase in enumerate(phrases):
                    text_segments.append({
                        "text": phrase["text"],
                        "start": i * segment_dur,
                        "end": (i + 1) * segment_dur - 0.1,
                    })

                output = work_dir / "_with_text.mp4"
                burn_text_overlays(
                    final_path, text_segments, output,
                    font_size=54, position=text_position,
                    outline_width=4, bg_opacity=0.4,
                )
                # Swap
                final_path.unlink(missing_ok=True)
                final_path = output

            _run("text_overlays", do_text)

            # ── 6. Finalize ──────────────────────────────────────────────
            def do_done():
                nonlocal final_path
                title_slug = topic.replace(" ", "_")[:40]
                dest = work_dir / f"{title_slug}_short.mp4"
                if final_path and final_path.exists() and final_path != dest:
                    import shutil
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
    title = script_data.get("title", topic) if script_data else topic
    rows: list[tuple[str, str]] = [
        ("Job ID", f"[id]{job.id}[/id]"),
        ("Title", f"[bold bright_white]{title}[/bold bright_white]"),
        ("Format", "9:16 Vertical (1080x1920)"),
        ("Source", "Pexels Stock Footage"),
    ]

    if final_path and final_path.exists():
        size_mb = final_path.stat().st_size / (1024 * 1024)
        rows.append(("Video", f"[path]{final_path}[/path]"))
        rows.append(("Size", f"{size_mb:.1f} MB"))

    from ytauto.services.ffmpeg import get_audio_duration
    if voiceover_path.exists():
        dur = get_audio_duration(voiceover_path)
        rows.append(("Duration", f"{int(dur)}s"))

    rows.append(("Clips", f"{len(clip_paths)} stock clips"))
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
        import subprocess as sp
        if platform.system() == "Darwin":
            sp.Popen(["open", str(final_path)])
