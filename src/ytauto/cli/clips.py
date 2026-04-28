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


def clips_rip(
    url: str = typer.Argument(help="YouTube URL to download and rip clips from."),
    tags: str = typer.Option(
        "", "--tags", "-t",
        help="Comma-separated tags for extracted clips (e.g., 'suits,business').",
    ),
    scene_threshold: float = typer.Option(
        0.3, "--threshold",
        help="Scene detection sensitivity (0.0-1.0, lower=more cuts).",
    ),
    keep_audio: bool = typer.Option(
        False, "--keep-audio",
        help="Keep audio track (default: strips voiceover/music).",
    ),
    min_duration: float = typer.Option(
        2.0, "--min-dur",
        help="Skip clips shorter than this (seconds).",
    ),
) -> None:
    """Download a video and rip clean movie/TV clips from it.

    Downloads the video, strips the voiceover/music/text overlay audio,
    detects scene cuts, and saves each individual movie clip to your library.

    Perfect for extracting Suits/movie footage from motivational channels.

    Example:
        ytauto clips-rip "https://youtube.com/shorts/..." --tags suits,business
    """
    from ytauto.services.cliprip import rip_clips
    from ytauto.services.clips import get_clips_dir

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    clips_dir = get_clips_dir()

    console.print()
    console.print(header("Ripping Clips", f"Source: {url}"))
    console.print()
    console.print("  [dim]This will:[/dim]")
    console.print("    [accent]1.[/accent] Download the video")
    console.print("    [accent]2.[/accent] Strip voiceover/music audio" if not keep_audio else "    [accent]2.[/accent] Keep audio track")
    console.print("    [accent]3.[/accent] Detect scene cuts (hard cuts between clips)")
    console.print("    [accent]4.[/accent] Save each clean clip to your library")
    console.print()

    try:
        with spinner("Downloading and splitting into clips..."):
            clips = rip_clips(
                url=url,
                clips_dir=clips_dir,
                tags=tag_list,
                min_clip_duration=min_duration,
                scene_threshold=scene_threshold,
                strip_audio=not keep_audio,
            )
    except Exception as exc:
        error(str(exc))
        raise typer.Exit(1)

    if not clips:
        warning("No clips extracted. Try lowering --threshold (e.g., 0.2) for more sensitivity.")
        return

    table = styled_table(f"Ripped {len(clips)} Clean Clips")
    table.add_column("#", style=f"bold {ACCENT}", width=3)
    table.add_column("ID", style="id", min_width=12)
    table.add_column("Duration", min_width=10)
    table.add_column("Tags", min_width=15)

    for i, clip in enumerate(clips, 1):
        table.add_row(
            str(i),
            clip["id"],
            f"{clip['duration']:.1f}s",
            ", ".join(clip.get("tags", [])) or "-",
        )

    console.print(table)
    console.print()
    success(f"{len(clips)} clean clips saved to library!")
    console.print(f"  [dim]Use them:[/dim] [accent]ytauto shorts \"topic\" --clips library[/accent]")
    if tag_list:
        console.print(f"  [dim]Filter:[/dim]  [accent]ytauto shorts \"topic\" --clips library --clip-tag {tag_list[0]}[/accent]")
    console.print()


def clips_extract(
    video: str = typer.Argument(help="Path to source video (movie, episode, etc.)."),
    source_name: str = typer.Option(
        "", "--source", "-s",
        help="Source label (e.g., 'Suits S01E01', 'Wolf of Wall Street').",
    ),
    tags: str = typer.Option(
        "", "--tags", "-t",
        help="Comma-separated tags for all extracted clips.",
    ),
) -> None:
    """Extract multiple clips from a movie/episode file interactively.

    Prompts you to enter start/end timestamps for each clip you want to extract.
    Great for pulling scenes from Netflix downloads, movie files, etc.

    Example timestamps: 00:05:30 to 00:05:50 (20 second clip)
    """
    from ytauto.services.clips import extract_clips

    video_path = Path(video).expanduser().resolve()
    if not video_path.exists():
        error(f"File not found: {video}")
        raise typer.Exit(1)

    source = source_name or video_path.stem
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    console.print()
    console.print(header("Clip Extraction", f"Source: {source}\nFile: {video_path.name}"))
    console.print()
    console.print("  [dim]Enter start and end timestamps for each clip.[/dim]")
    console.print("  [dim]Format: MM:SS or HH:MM:SS. Type 'done' when finished.[/dim]\n")

    timestamps: list[tuple[str, str]] = []
    clip_num = 1

    while True:
        console.print(f"  [accent]Clip {clip_num}:[/accent]")
        start = typer.prompt("    Start time (or 'done')", default="done")
        if start.lower() == "done":
            break
        end = typer.prompt("    End time")
        timestamps.append((start, end))
        clip_num += 1
        console.print()

    if not timestamps:
        console.print("  [dim]No clips to extract.[/dim]\n")
        return

    console.print()
    with spinner(f"Extracting {len(timestamps)} clips..."):
        extracted = extract_clips(
            video_path=video_path,
            timestamps=timestamps,
            tags=tag_list,
            source_name=source,
        )

    if not extracted:
        error("No clips were extracted successfully.")
        raise typer.Exit(1)

    table = styled_table(f"Extracted {len(extracted)} Clips")
    table.add_column("ID", style="id", min_width=12)
    table.add_column("Title", min_width=25)
    table.add_column("Duration", min_width=10)

    for clip in extracted:
        table.add_row(
            clip["id"],
            clip["title"],
            f"{clip['duration']:.0f}s",
        )

    console.print(table)
    console.print()
    success(f"{len(extracted)} clips added to library.\n")


def clips_shows() -> None:
    """Browse curated shows available for clip sourcing.

    Lists TV shows and movies with clean scene compilations on YouTube
    that are perfect for faceless Shorts content.
    """
    from ytauto.services.showlib import list_shows

    shows = list_shows()

    console.print()
    table = styled_table(f"Available Shows ({len(shows)})")
    table.add_column("#", style=f"bold {ACCENT}", width=3)
    table.add_column("ID", style="id", min_width=18)
    table.add_column("Show", min_width=22)
    table.add_column("Genre", min_width=20)
    table.add_column("Vibe", min_width=30)

    for i, show in enumerate(shows, 1):
        table.add_row(
            str(i),
            show["id"],
            show["name"],
            show.get("genre", "")[:18],
            show.get("vibe", "")[:28],
        )

    console.print(table)
    console.print()
    console.print("  [dim]Search for clips:[/dim]  [accent]ytauto clips-search suits[/accent]")
    console.print("  [dim]Bulk download:[/dim]    [accent]ytauto clips-bulk suits[/accent]\n")


def clips_search(
    show: str = typer.Argument(help="Show ID (e.g., 'suits', 'peaky-blinders'). See 'clips-shows' for list."),
    count: int = typer.Option(5, "--count", "-n", help="Max results."),
) -> None:
    """Search YouTube for clean scene compilations of a show."""
    from ytauto.services.showlib import search_show_videos, SHOW_CATALOG

    if show not in SHOW_CATALOG:
        error(f"Unknown show: {show}")
        console.print(f"  [dim]Available: {', '.join(SHOW_CATALOG.keys())}[/dim]\n")
        raise typer.Exit(1)

    show_info = SHOW_CATALOG[show]

    console.print()
    console.print(header(f"Searching: {show_info['name']}", show_info.get("vibe", "")))
    console.print()

    with spinner(f"Searching YouTube for {show_info['name']} compilations..."):
        results = search_show_videos(show, max_results=count)

    if not results:
        warning("No results found.")
        return

    table = styled_table(f"Found {len(results)} Compilations")
    table.add_column("#", style=f"bold {ACCENT}", width=3)
    table.add_column("Title", min_width=40)
    table.add_column("Channel", min_width=18)
    table.add_column("Duration", min_width=8)
    table.add_column("Views", min_width=10, justify="right")

    for i, v in enumerate(results, 1):
        views_str = f"{v['views']:,}" if v['views'] else "?"
        table.add_row(
            str(i),
            v["title"][:38],
            v["channel"][:16],
            f"{v['duration'] // 60}m",
            views_str,
        )

    console.print(table)
    console.print()
    console.print("  [dim]Rip clips from a video:[/dim]")
    console.print(f"  [accent]ytauto clips-rip \"{results[0]['url']}\" --tags {show}[/accent]\n")
    console.print("  [dim]Or bulk-download all:[/dim]")
    console.print(f"  [accent]ytauto clips-bulk {show}[/accent]\n")


def clips_bulk(
    show: str = typer.Argument(help="Show ID (e.g., 'suits', 'breaking-bad')."),
    max_videos: int = typer.Option(3, "--max", "-n", help="Max videos to download and rip."),
    scene_threshold: float = typer.Option(0.3, "--threshold", help="Scene detection sensitivity."),
) -> None:
    """Bulk download and rip clean clips from a show's YouTube compilations.

    Searches for the best scene compilations, downloads them, strips audio,
    splits into individual clips, and saves everything to your library.
    """
    from ytauto.services.showlib import search_show_videos, SHOW_CATALOG
    from ytauto.services.cliprip import rip_clips
    from ytauto.services.clips import get_clips_dir

    if show not in SHOW_CATALOG:
        error(f"Unknown show: {show}")
        console.print(f"  [dim]Available: {', '.join(SHOW_CATALOG.keys())}[/dim]\n")
        raise typer.Exit(1)

    show_info = SHOW_CATALOG[show]
    clips_dir = get_clips_dir()

    console.print()
    console.print(header(
        f"Bulk Ripping: {show_info['name']}",
        f"Downloading up to {max_videos} compilations, extracting clean clips",
    ))
    console.print()

    with spinner(f"Searching YouTube for {show_info['name']}..."):
        videos = search_show_videos(show, max_results=max_videos)

    if not videos:
        error("No compilations found.")
        raise typer.Exit(1)

    console.print(f"  [dim]Found {len(videos)} compilations. Starting rip...[/dim]\n")

    total_clips = 0
    for i, video in enumerate(videos, 1):
        console.print(f"  [accent]━━━ Video {i}/{len(videos)} ━━━[/accent]")
        console.print(f"  [bold bright_white]{video['title'][:60]}[/bold bright_white]")
        console.print(f"  [dim]{video['channel']} | {video['duration'] // 60}m | {video['views']:,} views[/dim]\n")

        try:
            with spinner(f"Downloading and ripping ({video['duration'] // 60}m video)..."):
                clips = rip_clips(
                    url=video["url"],
                    clips_dir=clips_dir,
                    tags=[show, show_info.get("genre", "").split(",")[0].strip()],
                    scene_threshold=scene_threshold,
                )
            success(f"{len(clips)} clips extracted")
            total_clips += len(clips)
        except Exception as exc:
            warning(f"Failed: {str(exc)[:100]}")

        console.print()

    console.print()
    success(f"Bulk rip complete! {total_clips} total clips from {len(videos)} videos.")
    console.print(f"  [dim]Use them:[/dim] [accent]ytauto shorts \"topic\" --clips library --clip-tag {show}[/accent]\n")
