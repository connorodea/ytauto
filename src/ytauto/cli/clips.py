"""Clip library management — add, import, list, delete clips for Shorts."""

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
    spinner,
)


def clips_add(
    url: str = typer.Argument(help="YouTube URL to download (video, Short, or clip)."),
    tags: str = typer.Option(
        "", "--tags", "-t",
        help="Comma-separated tags (e.g., 'suits,business,drama').",
    ),
    max_duration: int = typer.Option(
        120, "--max-duration",
        help="Skip videos longer than this (seconds).",
    ),
) -> None:
    """Download a video clip from YouTube and add to your clip library."""
    from ytauto.services.clips import download_clip

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    console.print()
    console.print(header("Adding Clip", f"Source: {url}"))
    console.print()

    try:
        with spinner("Downloading clip..."):
            meta = download_clip(url, tags=tag_list, max_duration=max_duration)
    except Exception as exc:
        error(str(exc))
        raise typer.Exit(1)

    console.print(result_panel("Clip Added", [
        ("ID", f"[id]{meta['id']}[/id]"),
        ("Title", meta["title"]),
        ("Source", meta["source"]),
        ("Duration", f"{meta['duration']}s"),
        ("Tags", ", ".join(meta.get("tags", [])) or "[dim]none[/dim]"),
    ]))
    console.print()
    success(f"Clip saved to library. Use it with: [accent]ytauto shorts \"topic\" --clips library[/accent]\n")


def clips_import(
    folder: str = typer.Argument(help="Path to folder containing video files."),
    tags: str = typer.Option(
        "", "--tags", "-t",
        help="Comma-separated tags for all imported clips.",
    ),
) -> None:
    """Import all video files from a folder into your clip library."""
    from ytauto.services.clips import import_folder

    folder_path = Path(folder).expanduser().resolve()
    if not folder_path.is_dir():
        error(f"Not a directory: {folder}")
        raise typer.Exit(1)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    console.print()
    console.print(header("Importing Clips", f"From: {folder_path}"))
    console.print()

    with spinner("Importing clips..."):
        imported = import_folder(folder_path, tags=tag_list)

    if not imported:
        warning("No video files found in the folder.")
        return

    table = styled_table(f"Imported {len(imported)} Clips")
    table.add_column("ID", style="id", min_width=12)
    table.add_column("Title", min_width=30)
    table.add_column("Duration", min_width=10)
    table.add_column("Tags", min_width=15)

    for clip in imported:
        table.add_row(
            clip["id"],
            clip["title"][:30],
            f"{clip['duration']:.0f}s",
            ", ".join(clip.get("tags", [])) or "-",
        )

    console.print(table)
    console.print()
    success(f"{len(imported)} clips imported to library.\n")


def clips_list(
    tag: str = typer.Option(
        None, "--tag", "-t",
        help="Filter by tag.",
    ),
) -> None:
    """List all clips in your clip library."""
    from ytauto.services.clips import list_clips

    clips = list_clips(tag=tag)

    console.print()
    if not clips:
        console.print("  [dim]No clips in library. Add some with:[/dim]")
        console.print('    [accent]ytauto clips-add "https://youtube.com/..."[/accent]')
        console.print("    [accent]ytauto clips-import ~/my-clips/[/accent]\n")
        return

    title = f"Clip Library ({len(clips)} clips)"
    if tag:
        title += f" — tag: {tag}"

    table = styled_table(title)
    table.add_column("#", style=f"bold {ACCENT}", width=3)
    table.add_column("ID", style="id", min_width=12)
    table.add_column("Title", min_width=30)
    table.add_column("Source", min_width=15)
    table.add_column("Duration", min_width=10)
    table.add_column("Tags", min_width=15)

    for i, clip in enumerate(clips, 1):
        table.add_row(
            str(i),
            clip["id"],
            clip["title"][:28],
            clip.get("source", "?")[:14],
            f"{clip.get('duration', 0):.0f}s",
            ", ".join(clip.get("tags", []))[:20] or "-",
        )

    console.print(table)
    console.print()


def clips_delete(
    clip_id: str = typer.Argument(help="Clip ID to delete."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
) -> None:
    """Delete a clip from your library."""
    from ytauto.services.clips import delete_clip, list_clips

    # Find the clip
    clips = list_clips()
    target = next((c for c in clips if c["id"] == clip_id), None)

    if not target:
        error(f"Clip not found: {clip_id}")
        raise typer.Exit(1)

    console.print()
    console.print(f"  [warn]Delete clip:[/warn]")
    console.print(f"    ID:    [id]{target['id']}[/id]")
    console.print(f"    Title: {target['title']}")
    console.print()

    if not force and not typer.confirm("  Are you sure?", default=False):
        console.print("  [dim]Cancelled.[/dim]\n")
        return

    delete_clip(clip_id)
    success(f"Clip [id]{clip_id}[/id] deleted.\n")
