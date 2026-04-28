"""Batch mode — process multiple video topics from a file."""

from __future__ import annotations

from pathlib import Path

import typer

from ytauto.cli.theme import (
    ACCENT,
    console,
    error,
    header,
    result_panel,
    styled_table,
    success,
    warning,
)
from ytauto.config.settings import get_settings
from ytauto.models.job import Job, JobStatus, PipelineStep
from ytauto.pipeline.context import PipelineContext
from ytauto.pipeline.orchestrator import PipelineError, PipelineOrchestrator
from ytauto.pipeline.stages import STAGE_REGISTRY
from ytauto.store.json_store import JsonDirectoryStore


def batch(
    file: str = typer.Argument(help="Path to file with topics (one per line, or .json)."),
    duration: str = typer.Option(
        "medium", "--duration", "-d",
        help="Video length for all videos: short, medium, long.",
    ),
    voice: str = typer.Option(
        None, "--voice", "-v",
        help="TTS voice for all videos.",
    ),
    engine: str = typer.Option(
        None, "--engine", "-e",
        help="LLM engine: claude or openai.",
    ),
    transition: str = typer.Option(
        "crossfade", "--transition", "-t",
        help="Transition style for all videos.",
    ),
    no_thumbnail: bool = typer.Option(
        False, "--no-thumbnail",
        help="Skip thumbnail generation for faster processing.",
    ),
) -> None:
    """Process multiple video topics from a text file (one topic per line)."""
    settings = get_settings()
    settings.ensure_directories()

    voice = voice or settings.default_tts_voice
    engine = engine or settings.default_llm_provider

    file_path = Path(file).expanduser().resolve()
    if not file_path.exists():
        error(f"File not found: {file}")
        raise typer.Exit(1)

    # Parse topics
    if file_path.suffix == ".json":
        import json
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            topics = [str(t) if isinstance(t, str) else t.get("topic", "") for t in data]
        else:
            error("JSON file must be a list of strings or objects with 'topic' key.")
            raise typer.Exit(1)
    else:
        raw = file_path.read_text(encoding="utf-8")
        topics = [line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")]

    if not topics:
        error("No topics found in file.")
        raise typer.Exit(1)

    console.print()
    console.print(header(
        f"Batch Processing — {len(topics)} Videos",
        f"Duration: {duration}  |  Voice: {voice}  |  Engine: {engine}  |  Transition: {transition}",
    ))
    console.print()

    # Preview
    for i, topic in enumerate(topics, 1):
        console.print(f"  [accent]{i:>3}.[/accent] {topic}")
    console.print()

    if not typer.confirm(f"  Process all {len(topics)} videos?", default=True):
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    orchestrator = PipelineOrchestrator(settings=settings)
    results: list[dict] = []

    for i, topic in enumerate(topics, 1):
        console.print(f"\n  [accent]━━━ Video {i}/{len(topics)} ━━━[/accent]")
        console.print(f'  [bold bright_white]{topic}[/bold bright_white]\n')

        # Create job
        job = Job(
            topic=topic, duration_config=duration,
            voice_config=voice, engine_config=engine,
        )
        work_dir = settings.workspaces_dir / job.id
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "media").mkdir(exist_ok=True)
        job.workspace_dir = str(work_dir)
        job.steps = [PipelineStep(name=name) for name, _ in STAGE_REGISTRY]
        job_store.save(job)

        ctx = PipelineContext(
            job_id=job.id, topic=topic, work_dir=work_dir,
            duration=duration, voice=voice, engine=engine,
            transition=transition, skip_thumbnail=no_thumbnail,
        )

        try:
            def on_done(name: str, idx: int, total: int, elapsed: float) -> None:
                console.print(f"    [success]\u2713[/success] {name} [dim]{elapsed:.1f}s[/dim]")

            orchestrator.run(ctx, job_store=job_store, on_stage_done=on_done)
            results.append({"topic": topic, "job_id": job.id, "status": "completed"})
            success(f"Video {i}/{len(topics)} complete — {job.id}")

        except PipelineError as exc:
            results.append({"topic": topic, "job_id": job.id, "status": "failed", "error": str(exc.original)})
            warning(f"Video {i}/{len(topics)} failed at {exc.stage}: {str(exc.original)[:100]}")
            console.print(f"    [dim]Resume: ytauto resume {job.id}[/dim]")

    # Summary table
    console.print()
    table = styled_table("Batch Results")
    table.add_column("#", width=3, style=f"bold {ACCENT}")
    table.add_column("Topic", min_width=30)
    table.add_column("Job ID", style="id", min_width=16)
    table.add_column("Status", min_width=12)

    from ytauto.cli.theme import status_badge
    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r["topic"][:40],
            r["job_id"],
            status_badge(r["status"]),
        )

    console.print(table)

    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    console.print()
    success(f"Batch complete: {completed} succeeded, {failed} failed out of {len(results)}.\n")
