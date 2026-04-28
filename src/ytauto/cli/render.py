"""Render command — assemble video from an existing job's assets."""

from __future__ import annotations

from pathlib import Path

import typer

from ytauto.cli.theme import console, error, header, spinner, success
from ytauto.config.settings import get_settings
from ytauto.models.job import Job
from ytauto.store.json_store import JsonDirectoryStore


def render(
    job_id: str = typer.Argument(help="Job ID to render video for."),
) -> None:
    """Render the final video from a job's images and voiceover."""
    settings = get_settings()

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    try:
        job = job_store.get(job_id)
    except FileNotFoundError:
        error(f"Job not found: {job_id}")
        raise typer.Exit(1)

    work_dir = Path(job.workspace_dir)
    media_dir = work_dir / "media"
    voiceover_path = work_dir / "voiceover.mp3"

    if not voiceover_path.exists():
        error("No voiceover.mp3 found. Generate voiceover first.")
        raise typer.Exit(1)

    image_paths = sorted(media_dir.glob("*.png")) + sorted(media_dir.glob("*.jpg"))
    if not image_paths:
        error("No images found in media/. Generate visuals first.")
        raise typer.Exit(1)

    console.print()
    console.print(header("Video Rendering", f"Job: {job_id} | Images: {len(image_paths)}"))
    console.print()

    title = job.topic.replace(" ", "_")[:50]
    output_path = work_dir / f"{title}.mp4"

    from ytauto.services.ffmpeg import assemble_video

    try:
        with spinner("Rendering video with ffmpeg..."):
            assemble_video(
                image_paths=image_paths,
                voiceover_path=voiceover_path,
                output_path=output_path,
                settings=settings,
            )
    except Exception as exc:
        error(f"Rendering failed: {exc}")
        raise typer.Exit(1)

    size_mb = output_path.stat().st_size / (1024 * 1024)

    job.video_path = str(output_path)
    job.touch()
    job_store.save(job)

    success(f"Video rendered: [path]{output_path}[/path]")
    console.print(f"  [dim]Size: {size_mb:.1f} MB[/dim]\n")
