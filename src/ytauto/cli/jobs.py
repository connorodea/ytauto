"""Job management commands — list, show, resume, delete."""

from __future__ import annotations

from pathlib import Path

import typer

from ytauto.cli.theme import (
    ACCENT,
    console,
    error,
    header,
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


def jobs(
    interactive: bool = typer.Option(
        False, "--interactive", "-i",
        help="Interactively select a job to view details.",
    ),
) -> None:
    """List all video creation jobs."""
    settings = get_settings()
    settings.ensure_directories()

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    all_jobs = job_store.list_all()

    console.print()
    if not all_jobs:
        console.print(
            '  [dim]No jobs yet. Create one with:[/dim]'
            ' [accent]ytauto create "topic"[/accent]\n'
        )
        return

    table = styled_table("Jobs")
    table.add_column("#", style=f"bold {ACCENT}", width=3)
    table.add_column("ID", style="id", min_width=16)
    table.add_column("Topic", min_width=30)
    table.add_column("Status", min_width=14)
    table.add_column("Duration", min_width=10)
    table.add_column("Created", min_width=18)

    for idx, j in enumerate(all_jobs, 1):
        created = j.created_at.strftime("%Y-%m-%d %H:%M")
        topic_display = j.topic[:40] + ("\u2026" if len(j.topic) > 40 else "")
        table.add_row(
            str(idx),
            j.id,
            topic_display,
            status_badge(j.status.value),
            j.duration_config,
            created,
        )

    console.print(table)
    console.print()

    # Interactive selection
    if interactive or typer.confirm("  View a job's details?", default=False):
        choice = typer.prompt(
            f"  Job # [1-{len(all_jobs)}]",
            default="1",
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(all_jobs):
                job(all_jobs[idx].id)
            else:
                error(f"Invalid selection: {choice}")
        except ValueError:
            # Try as job ID
            job(choice)


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

    # Main details panel
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

    status = "success" if j.status == JobStatus.completed else "error" if j.status == JobStatus.failed else "warning"
    console.print(result_panel("Job Details", rows, status=status))

    # Show error if present
    if j.error:
        console.print(f"\n  [error]\u2717 Error:[/error] [dim]{j.error}[/dim]")

    # Pipeline steps
    if j.steps:
        console.print()
        table = styled_table("Pipeline Steps")
        table.add_column("#", style="dim", width=3)
        table.add_column("Stage", min_width=22)
        table.add_column("Status", min_width=14)
        table.add_column("Error", style="dim", max_width=50)

        for i, step in enumerate(j.steps, 1):
            table.add_row(
                str(i),
                step.name,
                status_badge(step.status.value),
                (step.error or "")[:50],
            )

        console.print(table)

    # Output files
    if j.workspace_dir and Path(j.workspace_dir).exists():
        work_dir = Path(j.workspace_dir)
        files = []
        for f in sorted(work_dir.iterdir()):
            if f.is_file():
                size = f.stat().st_size
                if size > 1024 * 1024:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.0f} KB"
                else:
                    size_str = f"{size} B"
                files.append((f.name, size_str))

        if files:
            console.print()
            ftable = styled_table("Output Files")
            ftable.add_column("File", min_width=40)
            ftable.add_column("Size", justify="right", min_width=10)
            for name, size in files:
                ftable.add_row(name, size)
            console.print(ftable)

    console.print()

    # Actions hint
    if j.status == JobStatus.failed:
        console.print(f"  [dim]Resume:[/dim] [accent]ytauto resume {j.id}[/accent]\n")
    elif j.status == JobStatus.completed:
        video_path = None
        if j.workspace_dir:
            mp4s = list(Path(j.workspace_dir).glob("*.mp4"))
            if mp4s:
                video_path = mp4s[0]
        if video_path:
            console.print(f'  [dim]Open video:[/dim] [accent]open "{video_path}"[/accent]\n')


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
        error("No pipeline context found. Cannot resume \u2014 the job may not have started.")
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
