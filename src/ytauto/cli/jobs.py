"""Job management commands — list, show, resume, delete."""

from __future__ import annotations

from pathlib import Path

import typer

from ytauto.cli.theme import (
    console,
    error,
    header,
    kv,
    pipeline_progress,
    result_panel,
    status_badge,
    styled_table,
    success,
)
from ytauto.config.settings import get_settings
from ytauto.models.job import Job, JobStatus, PipelineStep
from ytauto.pipeline.context import PipelineContext
from ytauto.pipeline.orchestrator import PipelineError, PipelineOrchestrator
from ytauto.pipeline.stages import STAGE_REGISTRY
from ytauto.store.json_store import JsonDirectoryStore


def jobs() -> None:
    """List all video creation jobs."""
    settings = get_settings()
    settings.ensure_directories()

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    all_jobs = job_store.list_all()

    console.print()
    if not all_jobs:
        console.print('  [dim]No jobs yet. Create one with:[/dim] [accent]ytauto create "topic"[/accent]\n')
        return

    table = styled_table("Jobs")
    table.add_column("ID", style="id", min_width=16)
    table.add_column("Topic", min_width=30)
    table.add_column("Status", min_width=12)
    table.add_column("Duration", min_width=10)
    table.add_column("Created", min_width=18)

    for j in all_jobs:
        created = j.created_at.strftime("%Y-%m-%d %H:%M")
        table.add_row(
            j.id,
            j.topic[:40] + ("..." if len(j.topic) > 40 else ""),
            status_badge(j.status.value),
            j.duration_config,
            created,
        )

    console.print(table)
    console.print()


def job(
    job_id: str = typer.Argument(help="Job ID to inspect."),
) -> None:
    """Show detailed information about a specific job."""
    settings = get_settings()
    settings.ensure_directories()

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    try:
        j = job_store.get(job_id)
    except FileNotFoundError:
        error(f"Job not found: {job_id}")
        raise typer.Exit(1)

    console.print()
    rows = [
        ("Job ID", f"[id]{j.id}[/id]"),
        ("Topic", j.topic),
        ("Status", status_badge(j.status.value)),
        ("Engine", j.engine_config),
        ("Voice", j.voice_config),
        ("Duration", j.duration_config),
        ("Created", j.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")),
        ("Updated", j.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC")),
    ]

    if j.workspace_dir:
        rows.append(("Workspace", f"[path]{j.workspace_dir}[/path]"))
    if j.video_path:
        rows.append(("Video", f"[path]{j.video_path}[/path]"))
    if j.thumbnail_path:
        rows.append(("Thumbnail", f"[path]{j.thumbnail_path}[/path]"))
    if j.error:
        rows.append(("Error", f"[error]{j.error}[/error]"))

    console.print(result_panel("Job Details", rows))

    if j.steps:
        console.print()
        table = styled_table("Pipeline Steps")
        table.add_column("#", style="dim", width=3)
        table.add_column("Stage", min_width=22)
        table.add_column("Status", min_width=12)
        table.add_column("Error", style="dim")

        for i, step in enumerate(j.steps, 1):
            table.add_row(
                str(i),
                step.name,
                status_badge(step.status.value),
                (step.error or "")[:60],
            )

        console.print(table)

    console.print()


def resume(
    job_id: str = typer.Argument(help="Job ID to resume."),
) -> None:
    """Resume a failed or interrupted pipeline from where it stopped."""
    settings = get_settings()
    settings.ensure_directories()

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    try:
        j = job_store.get(job_id)
    except FileNotFoundError:
        error(f"Job not found: {job_id}")
        raise typer.Exit(1)

    if j.status == JobStatus.completed:
        success(f"Job {job_id} is already completed.")
        return

    work_dir = Path(j.workspace_dir)
    context_path = work_dir / "pipeline_context.json"

    if not context_path.exists():
        error("No pipeline context found. Cannot resume — the job may not have started.")
        raise typer.Exit(1)

    ctx = PipelineContext.load(work_dir)

    # Find the stage to resume from
    last_completed = ctx.completed_stages[-1] if ctx.completed_stages else None
    stage_names = [name for name, _ in STAGE_REGISTRY]

    if last_completed and last_completed in stage_names:
        resume_idx = stage_names.index(last_completed) + 1
        if resume_idx >= len(stage_names):
            success("All stages already completed.")
            return
        start_from = stage_names[resume_idx]
    else:
        start_from = stage_names[0]

    console.print()
    console.print(header("Resuming Pipeline", f"Job: {job_id} | From: {start_from}"))
    console.print()

    orchestrator = PipelineOrchestrator(settings=settings)

    # Ensure steps exist on job for tracking
    if not j.steps:
        j.steps = [PipelineStep(name=name) for name, _ in STAGE_REGISTRY]

    try:
        progress = pipeline_progress()
        remaining = len(stage_names) - stage_names.index(start_from)

        with progress:
            task = progress.add_task("Resuming...", total=remaining)

            def on_start(name: str, idx: int, total: int) -> None:
                progress.update(task, description=name)

            def on_done(name: str, idx: int, total: int, elapsed: float) -> None:
                progress.update(task, advance=1)

            orchestrator.run(
                ctx,
                job_store=job_store,
                start_from=start_from,
                on_stage_start=on_start,
                on_stage_done=on_done,
            )
    except PipelineError as exc:
        console.print()
        error(f"Pipeline failed again at stage [bold]{exc.stage}[/bold]")
        console.print(f"  [dim]{exc.original}[/dim]\n")
        raise typer.Exit(1)

    console.print()
    success(f"Job {job_id} completed successfully!")
    console.print(f"  [dim]View details: [accent]ytauto job {job_id}[/accent][/dim]\n")
