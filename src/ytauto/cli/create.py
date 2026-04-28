"""The hero command — full end-to-end video creation pipeline."""

from __future__ import annotations

from pathlib import Path

import typer

from ytauto.cli.theme import (
    console,
    error,
    header,
    pipeline_progress,
    result_panel,
    success,
)
from ytauto.config.settings import get_settings
from ytauto.models.job import Job, JobStatus, PipelineStep
from ytauto.pipeline.context import PipelineContext
from ytauto.pipeline.orchestrator import PipelineError, PipelineOrchestrator
from ytauto.pipeline.stages import STAGE_REGISTRY
from ytauto.store.json_store import JsonDirectoryStore


def create(
    topic: str = typer.Argument(help="The video topic or idea."),
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
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Show the pipeline plan without executing.",
    ),
) -> None:
    """Create a complete YouTube video from a topic using AI.

    Runs the full pipeline: script → SEO → voiceover → visuals → thumbnail → video.
    """
    settings = get_settings()
    settings.ensure_directories()

    voice = voice or settings.default_tts_voice
    engine = engine or settings.default_llm_provider

    # Create job
    job = Job(topic=topic, duration_config=duration, voice_config=voice, engine_config=engine)
    work_dir = settings.workspaces_dir / job.id
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "media").mkdir(exist_ok=True)
    job.workspace_dir = str(work_dir)

    # Build pipeline steps
    job.steps = [PipelineStep(name=name) for name, _ in STAGE_REGISTRY]

    # Persist job
    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    job_store.save(job)

    console.print()
    console.print(
        header(
            "Creating Video",
            f'Topic: "{topic}"  |  Duration: {duration}  |  Voice: {voice}  |  Engine: {engine}',
        )
    )
    console.print()

    if dry_run:
        console.print("  [dim]Pipeline stages:[/dim]")
        for i, (name, _) in enumerate(STAGE_REGISTRY, 1):
            console.print(f"    [accent]{i}.[/accent] {name}")
        console.print(f"\n  [dim]Job ID: {job.id}[/dim]")
        console.print("  [dim]Dry run — no stages executed.[/dim]\n")
        return

    # Build context
    ctx = PipelineContext(
        job_id=job.id,
        topic=topic,
        work_dir=work_dir,
        duration=duration,
        voice=voice,
        engine=engine,
    )

    # Run pipeline with progress display
    orchestrator = PipelineOrchestrator(settings=settings)

    progress = pipeline_progress()
    task_id = None

    def on_start(name: str, idx: int, total: int) -> None:
        nonlocal task_id
        if task_id is not None:
            progress.update(task_id, advance=1)
        else:
            task_id = progress.add_task(name, total=total)
        progress.update(task_id, description=name)

    def on_done(name: str, idx: int, total: int, elapsed: float) -> None:
        pass  # Progress bar auto-advances via on_start

    try:
        with progress:
            task_id = progress.add_task("Starting...", total=len(STAGE_REGISTRY))

            def on_start_inner(name: str, idx: int, total: int) -> None:
                progress.update(task_id, description=name)

            def on_done_inner(name: str, idx: int, total: int, elapsed: float) -> None:
                progress.update(task_id, advance=1)

            orchestrator.run(
                ctx,
                job_store=job_store,
                on_stage_start=on_start_inner,
                on_stage_done=on_done_inner,
            )

    except PipelineError as exc:
        console.print()
        error(f"Pipeline failed at stage [bold]{exc.stage}[/bold]")
        console.print(f"  [dim]{exc.original}[/dim]")
        console.print(f"\n  Resume with: [accent]ytauto resume {job.id}[/accent]\n")
        raise typer.Exit(1)

    # Reload job for final state
    job = job_store.get(job.id)

    # Build result rows
    rows: list[tuple[str, str]] = [
        ("Job ID", f"[id]{job.id}[/id]"),
        ("Title", ctx.script.get("title", topic) if ctx.script else topic),
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
        tags = ctx.seo_metadata.get("tags", [])[:5]
        if tags:
            rows.append(("Tags", ", ".join(tags)))

    console.print()
    console.print(result_panel("Pipeline Complete", rows))
    console.print()
    success("Your video is ready!")
    console.print(f"  [dim]View job: [accent]ytauto job {job.id}[/accent][/dim]\n")
