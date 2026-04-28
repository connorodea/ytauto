"""Shorts command — create vertical 9:16 YouTube Shorts with punchy hooks and bold captions."""

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
)
from ytauto.config.settings import get_settings
from ytauto.models.job import Job, PipelineStep
from ytauto.store.json_store import JsonDirectoryStore

# Shorts-specific pipeline stages
SHORTS_STAGES = [
    "script",
    "voiceover",
    "captions",
    "visuals",
    "render",
    "done",
]

STAGE_LABELS = {
    "script": ("Writing hook", "Generating viral Shorts script..."),
    "voiceover": ("Recording voice", "Deepgram Aura TTS narration..."),
    "captions": ("Transcribing", "Word-level timestamps for captions..."),
    "visuals": ("Creating visuals", "Generating vertical 9:16 images..."),
    "render": ("Rendering Short", "Ken Burns + fast cuts + caption burn..."),
    "done": ("Finishing", ""),
}


def _build_stage_table(
    stages: list[str], completed: set[str], current: str | None,
    failed: str | None, timings: dict[str, float],
) -> Table:
    table = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
    table.add_column("icon", width=3)
    table.add_column("stage", min_width=28)
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
    captions_style: str = typer.Option(
        "hormozi", "--captions", "-c",
        help="Caption style: hormozi, mrbeast, tiktok, pop, bounce, bold_centered.",
    ),
    open_after: bool = typer.Option(
        False, "--open",
        help="Open the Short in your default player after creation.",
    ),
) -> None:
    """Create a viral YouTube Short (vertical 9:16, 30-60s, bold captions).

    Optimized for scroll-stopping hooks, rapid pacing, and punchy delivery.
    """
    settings = get_settings()
    settings.ensure_directories()

    voice = voice or settings.default_tts_voice
    engine = engine or settings.default_llm_provider
    seconds = max(30, min(60, seconds))

    # Interactive topic prompt if not provided
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
    (work_dir / "media").mkdir(exist_ok=True)
    job.workspace_dir = str(work_dir)
    job.steps = [PipelineStep(name=name) for name in SHORTS_STAGES]

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    job_store.save(job)

    console.print()
    console.print(header(
        "Creating YouTube Short",
        f'"{topic}"\n'
        f"Duration: {seconds}s  \u2502  Voice: {voice}  \u2502  Captions: {captions_style}  \u2502  Job: {job.id}",
    ))
    console.print()

    completed: set[str] = set()
    timings: dict[str, float] = {}
    current_stage: str | None = None

    try:
        with Live(
            _build_stage_table(SHORTS_STAGES, completed, None, None, timings),
            console=console, refresh_per_second=4,
        ) as live:

            def _run_stage(name: str, fn):
                nonlocal current_stage
                current_stage = name
                live.update(_build_stage_table(SHORTS_STAGES, completed, current_stage, None, timings))
                t0 = time.monotonic()
                fn()
                elapsed = time.monotonic() - t0
                completed.add(name)
                timings[name] = elapsed
                live.update(_build_stage_table(SHORTS_STAGES, completed, None, None, timings))

            # ── Stage 1: Script ──────────────────────────────────────────
            script_data = {}

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
                # Build narration
                parts = [script_data.get("hook", "")]
                for s in script_data.get("sections", []):
                    parts.append(s.get("narration", ""))
                parts.append(script_data.get("outro", ""))
                narration = "\n\n".join(p for p in parts if p)
                (work_dir / "narration.txt").write_text(narration, encoding="utf-8")

            _run_stage("script", do_script)

            # ── Stage 2: Voiceover ───────────────────────────────────────
            voiceover_path = work_dir / "voiceover.mp3"

            def do_voiceover():
                from ytauto.services.tts import synthesize_voiceover
                narration = (work_dir / "narration.txt").read_text(encoding="utf-8")
                synthesize_voiceover(narration, voiceover_path, voice=voice, settings=settings)

            _run_stage("voiceover", do_voiceover)

            # ── Stage 3: Captions (word timestamps) ──────────────────────
            word_timestamps = []

            def do_captions():
                nonlocal word_timestamps
                from ytauto.video.captions import transcribe_for_timestamps
                ts_path = work_dir / "word_timestamps.json"
                word_timestamps = transcribe_for_timestamps(voiceover_path, ts_path)

            _run_stage("captions", do_captions)

            # ── Stage 4: Visuals (vertical 9:16) ─────────────────────────
            media_paths: list[Path] = []

            def do_visuals():
                nonlocal media_paths
                from ytauto.services.imagegen import generate_images
                sections = script_data.get("sections", [])
                # Override visual prompts to be vertical
                for s in sections:
                    vp = s.get("visual_prompt", s.get("narration", "abstract"))
                    s["visual_prompt"] = (
                        f"Vertical 9:16 portrait composition, dramatic close-up, "
                        f"dark cinematic lighting, high contrast, moody: {vp}"
                    )
                media_paths = generate_images(
                    sections=sections, output_dir=work_dir / "media", settings=settings,
                )

            _run_stage("visuals", do_visuals)

            # ── Stage 5: Render (vertical with Ken Burns + captions) ─────
            final_path: Path | None = None

            def do_render():
                nonlocal final_path
                from ytauto.services.ffmpeg import get_audio_duration
                audio_dur = get_audio_duration(voiceover_path)
                n_images = len(media_paths)
                if n_images == 0:
                    raise RuntimeError("No images generated.")
                img_dur = max(2.0, audio_dur / n_images)

                # Render each image with Ken Burns at 1080x1920 (vertical)
                import subprocess
                import random
                clip_paths: list[Path] = []
                for i, img in enumerate(sorted(media_paths)):
                    clip = work_dir / f"_short_clip_{i:03d}.mp4"
                    total_frames = int(img_dur * 30)
                    zoom_in = random.choice([True, False])
                    z_expr = f"min(1+0.15*on/{total_frames},1.15)" if zoom_in else f"1.15-0.15*on/{total_frames}"
                    x_expr = "iw/2-(iw/zoom/2)"
                    y_expr = "ih/2-(ih/zoom/2)"
                    filt = (
                        f"scale=2160:3840,zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
                        f"d={total_frames}:s=1080x1920:fps=30,setsar=1"
                    )
                    subprocess.run([
                        "ffmpeg", "-y", "-loop", "1", "-framerate", "30",
                        "-i", str(img), "-filter_complex", filt,
                        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
                        "-pix_fmt", "yuv420p", "-t", str(img_dur),
                        str(clip),
                    ], capture_output=True, check=True)
                    clip_paths.append(clip)

                # Fast-cut concatenation (short clips = hard cuts work best)
                from ytauto.video.transitions import join_clips_with_transition
                joined = work_dir / "_short_joined.mp4"
                join_clips_with_transition(clip_paths, joined, transition="cut")

                # Mux with voiceover
                muxed = work_dir / "_short_muxed.mp4"
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", str(joined), "-i", str(voiceover_path),
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", str(muxed),
                ], capture_output=True, check=True)

                # Burn captions if ASS filter available
                from ytauto.services.ffmpeg import _has_filter
                if word_timestamps and _has_filter("ass"):
                    from ytauto.video.captions import generate_ass_captions, burn_captions, CaptionStyle, CAPTION_PRESETS
                    ass_path = work_dir / "captions.ass"
                    style = CAPTION_PRESETS.get(captions_style, CAPTION_PRESETS["hormozi"])
                    generate_ass_captions(
                        word_timestamps, ass_path, style=style,
                        video_width=1080, video_height=1920,
                    )
                    captioned = work_dir / "_short_captioned.mp4"
                    burn_captions(muxed, ass_path, captioned)
                    final_source = captioned
                else:
                    # Still generate ASS file for external use
                    if word_timestamps:
                        from ytauto.video.captions import generate_ass_captions, CAPTION_PRESETS
                        ass_path = work_dir / "captions.ass"
                        style = CAPTION_PRESETS.get(captions_style, CAPTION_PRESETS["hormozi"])
                        generate_ass_captions(
                            word_timestamps, ass_path, style=style,
                            video_width=1080, video_height=1920,
                        )
                    final_source = muxed

                # Move to final output
                title_slug = topic.replace(" ", "_")[:40]
                final_path = work_dir / f"{title_slug}_short.mp4"
                import shutil
                shutil.move(str(final_source), str(final_path))

                # Cleanup
                for f in work_dir.glob("_short_*.mp4"):
                    f.unlink(missing_ok=True)
                for f in work_dir.glob("_short_*.mp4"):
                    f.unlink(missing_ok=True)

            _run_stage("render", do_render)

            # ── Stage 6: Done ────────────────────────────────────────────
            def do_done():
                job.status = "completed"
                if final_path:
                    job.video_path = str(final_path)
                job.touch()
                job_store.save(job)

            _run_stage("done", do_done)

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
    ]

    if final_path and final_path.exists():
        size_mb = final_path.stat().st_size / (1024 * 1024)
        rows.append(("Video", f"[path]{final_path}[/path]"))
        rows.append(("Size", f"{size_mb:.1f} MB"))

    from ytauto.services.ffmpeg import get_audio_duration
    if voiceover_path.exists():
        dur = get_audio_duration(voiceover_path)
        rows.append(("Duration", f"{int(dur)}s"))

    rows.append(("Captions", captions_style))
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
