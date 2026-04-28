"""YouTube upload command."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ytauto.cli.theme import console, error, header, result_panel, spinner, success, warning
from ytauto.config.settings import get_settings
from ytauto.models.job import Job
from ytauto.store.json_store import JsonDirectoryStore


def upload(
    job_id: str = typer.Argument(help="Job ID to upload to YouTube."),
    privacy: str = typer.Option(
        "private", "--privacy", "-p",
        help="Privacy status: private, unlisted, or public.",
    ),
    title_override: str = typer.Option(
        None, "--title", "-t",
        help="Override the video title.",
    ),
) -> None:
    """Upload a completed video to YouTube."""
    settings = get_settings()

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    try:
        job = job_store.get(job_id)
    except FileNotFoundError:
        error(f"Job not found: {job_id}")
        raise typer.Exit(1)

    work_dir = Path(job.workspace_dir)

    # Find the video file
    video_files = list(work_dir.glob("*.mp4"))
    if not video_files:
        error("No MP4 video found in job workspace. Run the pipeline first.")
        raise typer.Exit(1)
    video_path = video_files[0]

    # Load SEO metadata
    seo_path = work_dir / "seo.json"
    seo: dict = {}
    if seo_path.exists():
        seo = json.loads(seo_path.read_text(encoding="utf-8"))

    title = title_override or seo.get("title", job.topic)
    description = seo.get("description", f"Video about: {job.topic}")
    tags = seo.get("tags", [])

    # Check for thumbnail
    thumbnail_path = work_dir / "thumbnail.png"
    has_thumb = thumbnail_path.exists()

    console.print()
    console.print(header("YouTube Upload", f"Job: {job_id}"))
    console.print()

    rows = [
        ("Title", title[:70]),
        ("Privacy", privacy),
        ("Tags", str(len(tags))),
        ("Thumbnail", "Yes" if has_thumb else "No"),
        ("Video", f"[path]{video_path.name}[/path]"),
    ]
    console.print(result_panel("Upload Preview", rows, status="warning"))
    console.print()

    if not typer.confirm("  Proceed with upload?", default=True):
        console.print("  [dim]Upload cancelled.[/dim]\n")
        return

    from ytauto.services.youtube import upload_video

    try:
        with spinner("Uploading to YouTube..."):
            result = upload_video(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                privacy=privacy,
                thumbnail_path=thumbnail_path if has_thumb else None,
            )
    except FileNotFoundError as exc:
        error(str(exc))
        raise typer.Exit(1)
    except Exception as exc:
        error(f"Upload failed: {exc}")
        raise typer.Exit(1)

    # Update job
    job.youtube_url = result["url"]
    job.touch()
    job_store.save(job)

    console.print()
    console.print(result_panel("Upload Complete", [
        ("Video ID", result["video_id"]),
        ("URL", f"[url]{result['url']}[/url]"),
        ("Status", result["status"]),
        ("Thumbnail", "Set" if result.get("thumbnail_set") else "Not set"),
    ]))
    console.print()
    success(f"Video uploaded! [url]{result['url']}[/url]\n")
