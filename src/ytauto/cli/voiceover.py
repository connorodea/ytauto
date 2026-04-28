"""Voiceover generation command — generate TTS audio for an existing job."""

from __future__ import annotations

from pathlib import Path

import typer

from ytauto.cli.theme import console, error, header, spinner, success
from ytauto.config.settings import get_settings
from ytauto.models.job import Job
from ytauto.store.json_store import JsonDirectoryStore


def voiceover(
    job_id: str = typer.Argument(help="Job ID to generate voiceover for."),
    voice: str = typer.Option(
        None, "--voice", "-v",
        help="TTS voice (alloy, echo, fable, onyx, nova, shimmer).",
    ),
) -> None:
    """Generate voiceover audio for an existing job's script."""
    settings = get_settings()
    voice = voice or settings.default_tts_voice

    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    try:
        job = job_store.get(job_id)
    except FileNotFoundError:
        error(f"Job not found: {job_id}")
        raise typer.Exit(1)

    work_dir = Path(job.workspace_dir)
    narration_path = work_dir / "narration.txt"

    if not narration_path.exists():
        error("No narration.txt found. Generate a script first with 'ytauto create' or 'ytauto script'.")
        raise typer.Exit(1)

    console.print()
    console.print(header("Voiceover Generation", f"Job: {job_id} | Voice: {voice}"))
    console.print()

    narration = narration_path.read_text(encoding="utf-8")
    output_path = work_dir / "voiceover.mp3"

    from ytauto.services.tts import synthesize_voiceover

    try:
        with spinner("Generating voiceover..."):
            synthesize_voiceover(
                text=narration,
                output_path=output_path,
                voice=voice,
                settings=settings,
            )
    except Exception as exc:
        error(f"Voiceover generation failed: {exc}")
        raise typer.Exit(1)

    from ytauto.services.ffmpeg import get_audio_duration
    duration = get_audio_duration(output_path)
    mins = int(duration // 60)
    secs = int(duration % 60)

    job.voiceover_path = str(output_path)
    job.touch()
    job_store.save(job)

    success(f"Voiceover saved to [path]{output_path}[/path]")
    console.print(f"  [dim]Duration: {mins}m {secs}s[/dim]\n")
