"""Open command — open a job's video in the default player."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import typer

from ytauto.cli.theme import console, error, success
from ytauto.config.settings import get_settings
from ytauto.models.job import Job
from ytauto.store.json_store import JsonDirectoryStore


def open_video(
    job_id: str = typer.Argument(help="Job ID whose video to open."),
) -> None:
    """Open the completed video in your default media player."""
    settings = get_settings()

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    try:
        job = job_store.get(job_id)
    except FileNotFoundError:
        error(f"Job not found: {job_id}")
        raise typer.Exit(1)

    work_dir = Path(job.workspace_dir)
    video_files = list(work_dir.glob("*.mp4"))

    if not video_files:
        error("No video found for this job. Run the pipeline first.")
        raise typer.Exit(1)

    video_path = video_files[0]

    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", str(video_path)])
    elif system == "Linux":
        subprocess.Popen(["xdg-open", str(video_path)])
    elif system == "Windows":
        subprocess.Popen(["start", str(video_path)], shell=True)
    else:
        console.print(f"  [dim]Open manually: {video_path}[/dim]")
        return

    success(f"Opening [path]{video_path.name}[/path]")


def delete_job(
    job_id: str = typer.Argument(help="Job ID to delete."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
) -> None:
    """Delete a job and its workspace files."""
    import shutil

    settings = get_settings()
    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)

    try:
        job = job_store.get(job_id)
    except FileNotFoundError:
        error(f"Job not found: {job_id}")
        raise typer.Exit(1)

    console.print()
    console.print(f"  [warn]This will permanently delete:[/warn]")
    console.print(f"    Job:       [id]{job.id}[/id]")
    console.print(f"    Topic:     {job.topic}")
    if job.workspace_dir:
        console.print(f"    Workspace: [path]{job.workspace_dir}[/path]")
    console.print()

    if not force and not typer.confirm("  Are you sure?", default=False):
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    # Delete workspace
    if job.workspace_dir and Path(job.workspace_dir).exists():
        shutil.rmtree(job.workspace_dir, ignore_errors=True)

    # Delete job record
    job_store.delete(job_id)

    success(f"Job [id]{job_id}[/id] deleted.\n")
