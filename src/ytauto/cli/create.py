"""The hero command — full end-to-end video creation pipeline."""

from __future__ import annotations

import time

import typer
from rich.live import Live
from rich.table import Table
from rich.text import Text

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
from ytauto.pipeline.context import PipelineContext
from ytauto.pipeline.orchestrator import PipelineError, PipelineOrchestrator
from ytauto.pipeline.stages import STAGE_REGISTRY
from ytauto.store.json_store import JsonDirectoryStore

# Friendly labels for each stage
STAGE_LABELS = {
    "script_generation": ("Writing script", "Generating video script with AI..."),
    "seo_generation": ("Optimizing SEO", "Creating title, tags, and description..."),
    "voiceover": ("Recording voice", "Generating voiceover narration..."),
    "visual_generation": ("Creating visuals", "Generating images for each section..."),
    "thumbnail_generation": ("Designing thumbnail", "Creating a clickable thumbnail..."),
    "video_assembly": ("Rendering video", "Assembling final video with ffmpeg..."),
    "summary": ("Finishing up", "Finalizing job..."),
}


def _build_stage_table(
    stages: list[tuple[str, str]],
    completed: set[str],
    current: str | None,
    failed: str | None,
    timings: dict[str, float],
) -> Table:
    """Build a live-updating stage status table."""
    table = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 2),
        pad_edge=True,
    )
    table.add_column("icon", width=3)
    table.add_column("stage", min_width=28)
    table.add_column("time", width=8, justify="right")

    for name, _ in stages:
        label, detail = STAGE_LABELS.get(name, (name, ""))

        if name in completed:
            icon = f"[bold {SUCCESS}]\u2713[/bold {SUCCESS}]"
            elapsed = timings.get(name, 0)
            time_str = f"[dim]{elapsed:.1f}s[/dim]"
            text = f"[dim]{label}[/dim]"
        elif name == failed:
            icon = f"[bold {ERROR}]\u2717[/bold {ERROR}]"
            time_str = ""
            text = f"[bold {ERROR}]{label}[/bold {ERROR}]"
        elif name == current:
            icon = f"[bold {ACCENT}]\u25b8[/bold {ACCENT}]"
            time_str = f"[{ACCENT}]...[/{ACCENT}]"
            text = f"[bold bright_white]{label}[/bold bright_white]  [{ACCENT_DIM}]{detail}[/{ACCENT_DIM}]"
        else:
            icon = "[dim]\u2022[/dim]"
            time_str = ""
            text = f"[dim]{label}[/dim]"

        table.add_row(icon, text, time_str)

    return table


def create(
    topic: str = typer.Argument(None, help="The video topic or idea."),
    duration: str = typer.Option(
        "medium", "--duration", "-d",
        help="Video length: short (~5m), medium (~10m), long (~18m).",
    ),
    voice: str = typer.Option(
        None, "--voice", "-v",
        help="TTS voice (alloy, echo, fable, onyx, nova, shimmer).",
    ),
    engine: str = typer.Option(
        None, "--engine", "-e",
        help="LLM engine: claude or openai.",
    ),
    channel: str = typer.Option(
        None, "--channel", "-c",
        help="Channel profile ID (use 'ytauto channels' to list).",
    ),
    music: str = typer.Option(
        None, "--music", "-m",
        help="Path to background music MP3 file.",
    ),
    open_after: bool = typer.Option(
        False, "--open",
        help="Open the video in your default player after creation.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Show the pipeline plan without executing.",
    ),
) -> None:
    """Create a complete YouTube video from a topic using AI.

    Runs the full pipeline: script \u2192 SEO \u2192 voiceover \u2192 visuals \u2192 thumbnail \u2192 video.
    """
    settings = get_settings()
    settings.ensure_directories()

    # Interactive topic prompt if not provided
    if not topic:
        console.print()
        console.print(header("New Video", "What should the video be about?"))
        console.print()
        topic = typer.prompt("  Topic")
        if not topic.strip():
            error("Topic cannot be empty.")
            raise typer.Exit(1)

        # Interactive duration selection
        console.print()
        console.print("  [dim]Duration options:[/dim]")
        console.print(f"    [accent]1.[/accent] short   (~5 min, 4 sections)")
        console.print(f"    [accent]2.[/accent] medium  (~10 min, 6 sections)")
        console.print(f"    [accent]3.[/accent] long    (~18 min, 8 sections)")
        console.print()
        dur_choice = typer.prompt("  Duration [1/2/3]", default="2")
        duration = {"1": "short", "2": "medium", "3": "long"}.get(dur_choice, "medium")

        # Interactive voice selection — Deepgram Aura voices
        dg_voices = [
            ("aura-orion-en", "Orion \u2014 male, deep & authoritative"),
            ("aura-arcas-en", "Arcas \u2014 male, warm & engaging"),
            ("aura-perseus-en", "Perseus \u2014 male, confident"),
            ("aura-zeus-en", "Zeus \u2014 male, powerful"),
            ("aura-asteria-en", "Asteria \u2014 female, warm"),
            ("aura-luna-en", "Luna \u2014 female, soft"),
            ("aura-stella-en", "Stella \u2014 female, bright"),
            ("aura-athena-en", "Athena \u2014 female, professional"),
        ]
        console.print()
        console.print("  [dim]Deepgram Aura voices:[/dim]")
        for i, (vid, desc) in enumerate(dg_voices, 1):
            marker = " [accent](default)[/accent]" if vid == "aura-orion-en" else ""
            console.print(f"    [accent]{i}.[/accent] {desc}{marker}")
        console.print()
        voice_choice = typer.prompt("  Voice [1-8]", default="1")
        try:
            voice = dg_voices[int(voice_choice) - 1][0]
        except (ValueError, IndexError):
            voice = "aura-orion-en"

        console.print()

    voice = voice or settings.default_tts_voice
    engine = engine or settings.default_llm_provider

    # Load channel profile if specified
    channel_context = None
    if channel:
        from ytauto.models.channel import ChannelProfile
        channels_dir = settings.data_dir / "channels"
        ch_store = JsonDirectoryStore[ChannelProfile](channels_dir, ChannelProfile)
        try:
            profile = ch_store.get(channel)
            channel_context = profile.to_prompt_context()
            voice = voice or profile.voice_profile
        except FileNotFoundError:
            from ytauto.cli.theme import warning
            warning(f"Channel profile '{channel}' not found. Using defaults.")

    # Validate music path
    music_path = None
    if music:
        from pathlib import Path as P
        mp = P(music).expanduser().resolve()
        if mp.exists():
            music_path = mp
        else:
            from ytauto.cli.theme import warning
            warning(f"Music file not found: {music}. Proceeding without background music.")

    # Create job
    job = Job(topic=topic, duration_config=duration, voice_config=voice, engine_config=engine)
    work_dir = settings.workspaces_dir / job.id
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "media").mkdir(exist_ok=True)
    job.workspace_dir = str(work_dir)
    job.steps = [PipelineStep(name=name) for name, _ in STAGE_REGISTRY]

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    job_store.save(job)

    # Header
    extras = f"Duration: {duration}  \u2502  Voice: {voice}  \u2502  Engine: {engine}"
    if channel and channel_context:
        extras += f"  \u2502  Channel: {channel}"
    if music_path:
        extras += f"  \u2502  Music: \u2713"
    extras += f"  \u2502  Job: {job.id}"

    console.print()
    console.print(header("Creating Video", f'"{topic}"\n{extras}'))
    console.print()

    if dry_run:
        table = _build_stage_table(
            STAGE_REGISTRY, set(), None, None, {},
        )
        console.print(table)
        console.print(f"\n  [dim]Dry run \u2014 no stages executed.[/dim]\n")
        return

    # Build context
    ctx = PipelineContext(
        job_id=job.id, topic=topic, work_dir=work_dir,
        duration=duration, voice=voice, engine=engine,
        channel_id=channel, channel_context=channel_context,
        music_path=music_path,
    )

    # Run pipeline with live stage display
    orchestrator = PipelineOrchestrator(settings=settings)
    completed: set[str] = set()
    current_stage: str | None = None
    failed_stage: str | None = None
    timings: dict[str, float] = {}
    stage_start_time: float = 0

    def on_start(name: str, idx: int, total: int) -> None:
        nonlocal current_stage, stage_start_time
        current_stage = name
        stage_start_time = time.monotonic()
        live.update(_build_stage_table(STAGE_REGISTRY, completed, current_stage, None, timings))

    def on_done(name: str, idx: int, total: int, elapsed: float) -> None:
        completed.add(name)
        timings[name] = elapsed
        live.update(_build_stage_table(STAGE_REGISTRY, completed, None, None, timings))

    try:
        with Live(
            _build_stage_table(STAGE_REGISTRY, completed, None, None, timings),
            console=console,
            refresh_per_second=4,
        ) as live:
            orchestrator.run(
                ctx,
                job_store=job_store,
                on_stage_start=on_start,
                on_stage_done=on_done,
            )

    except PipelineError as exc:
        failed_stage = exc.stage
        console.print(_build_stage_table(STAGE_REGISTRY, completed, None, failed_stage, timings))
        console.print()
        error(f"Pipeline failed at [bold]{exc.stage}[/bold]: {exc.original}")
        console.print()
        console.print(f"  [dim]Resume with:[/dim] [accent]ytauto resume {job.id}[/accent]\n")
        raise typer.Exit(1)

    # Reload job
    job = job_store.get(job.id)

    # Build gorgeous result panel
    title = ctx.script.get("title", topic) if ctx.script else topic
    rows: list[tuple[str, str]] = [
        ("Job ID", f"[id]{job.id}[/id]"),
        ("Title", f"[bold bright_white]{title}[/bold bright_white]"),
    ]

    if ctx.final_video_path and ctx.final_video_path.exists():
        size_mb = ctx.final_video_path.stat().st_size / (1024 * 1024)
        rows.append(("Video", f"[path]{ctx.final_video_path}[/path]"))
        rows.append(("Size", f"{size_mb:.1f} MB"))
    if ctx.thumbnail_path and ctx.thumbnail_path.exists():
        rows.append(("Thumbnail", f"[path]{ctx.thumbnail_path}[/path]"))
    if ctx.voiceover_duration:
        mins = int(ctx.voiceover_duration // 60)
        secs = int(ctx.voiceover_duration % 60)
        rows.append(("Duration", f"{mins}m {secs}s"))
    if ctx.seo_metadata:
        seo_title = ctx.seo_metadata.get("title", "")
        if seo_title:
            rows.append(("SEO Title", seo_title))
        tags = ctx.seo_metadata.get("tags", [])[:5]
        if tags:
            rows.append(("Top Tags", ", ".join(tags)))
    if ctx.media_paths:
        rows.append(("Images", f"{len(ctx.media_paths)} generated"))

    total_time = sum(timings.values())
    rows.append(("Total Time", f"{total_time:.0f}s"))

    console.print()
    console.print(result_panel("Video Created Successfully", rows))
    console.print()
    success("Your video is ready!")
    console.print(f"  [dim]View details:[/dim]  [accent]ytauto job {job.id}[/accent]")
    console.print(f"  [dim]Upload:[/dim]        [accent]ytauto upload {job.id}[/accent]")
    console.print(f"  [dim]Open video:[/dim]   [accent]ytauto open {job.id}[/accent]\n")

    # Auto-open if requested
    if open_after and ctx.final_video_path and ctx.final_video_path.exists():
        import platform
        import subprocess as sp
        system = platform.system()
        if system == "Darwin":
            sp.Popen(["open", str(ctx.final_video_path)])
        elif system == "Linux":
            sp.Popen(["xdg-open", str(ctx.final_video_path)])
