"""Channel profile management commands."""

from __future__ import annotations

import re

import typer

from ytauto.cli.theme import (
    ACCENT,
    console,
    error,
    header,
    result_panel,
    status_badge,
    styled_table,
    success,
    step,
)
from ytauto.config.settings import get_settings
from ytauto.models.channel import ChannelProfile
from ytauto.store.json_store import JsonDirectoryStore


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_]+", "-", text)[:30]


def channels() -> None:
    """List all channel profiles."""
    settings = get_settings()
    channels_dir = settings.data_dir / "channels"
    channels_dir.mkdir(parents=True, exist_ok=True)

    store = JsonDirectoryStore[ChannelProfile](channels_dir, ChannelProfile)
    all_channels = store.list_all()

    console.print()
    if not all_channels:
        console.print("  [dim]No channels yet. Create one with:[/dim] [accent]ytauto channel-add[/accent]")
        console.print("  [dim]Or use the default profile automatically.[/dim]\n")
        return

    table = styled_table("Channel Profiles")
    table.add_column("ID", style="id", min_width=16)
    table.add_column("Name", min_width=24)
    table.add_column("Niche", min_width=20)
    table.add_column("Tone", min_width=14)
    table.add_column("Voice", min_width=10)

    for ch in all_channels:
        table.add_row(ch.id, ch.name, ch.niche or "[dim]-[/dim]", ch.tone, ch.voice_profile)

    console.print(table)
    console.print()


def channel_add() -> None:
    """Create a new channel profile interactively."""
    settings = get_settings()
    channels_dir = settings.data_dir / "channels"
    channels_dir.mkdir(parents=True, exist_ok=True)

    store = JsonDirectoryStore[ChannelProfile](channels_dir, ChannelProfile)

    console.print()
    console.print(header("New Channel Profile", "Define your channel's brand voice and style."))

    step(1, "Channel Name")
    name = typer.prompt("  Name")
    channel_id = _slugify(name)

    step(2, "Niche [dim](e.g., 'macro finance', 'true crime', 'AI technology')[/dim]")
    niche = typer.prompt("  Niche", default="")

    step(3, "Target Audience [dim](e.g., 'curious millennials who like deep dives')[/dim]")
    audience = typer.prompt("  Audience", default="")

    step(4, "Tone")
    console.print("  [dim]Options: authoritative, conversational, dramatic, educational, humorous[/dim]")
    tone = typer.prompt("  Tone", default="authoritative")

    step(5, "Visual Style")
    console.print("  [dim]Describes the look for generated images and thumbnails[/dim]")
    visual = typer.prompt("  Style", default="dark cinematic, high contrast, dramatic lighting")

    step(6, "Default Voice")
    voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    console.print(f"  [dim]Options: {', '.join(voices)}[/dim]")
    voice = typer.prompt("  Voice", default="onyx")

    step(7, "Content Pillars [dim](comma-separated topics the channel covers)[/dim]")
    pillars_raw = typer.prompt("  Pillars", default="")
    pillars = [p.strip() for p in pillars_raw.split(",") if p.strip()] if pillars_raw else []

    step(8, "Outro CTA [dim](call to action for the end of every video)[/dim]")
    outro = typer.prompt("  Outro", default="If this opened your eyes, smash that subscribe button and hit the bell.")

    profile = ChannelProfile(
        id=channel_id,
        name=name,
        niche=niche,
        target_audience=audience,
        tone=tone,
        visual_style=visual,
        voice_profile=voice if voice in voices else "onyx",
        content_pillars=pillars,
        outro_template=outro,
    )

    store.save(profile)

    console.print()
    success(f"Channel [accent]{name}[/accent] saved as [id]{channel_id}[/id]")
    console.print(f"  [dim]Use it with:[/dim] [accent]ytauto create \"topic\" --channel {channel_id}[/accent]\n")


def channel_show(
    channel_id: str = typer.Argument(help="Channel profile ID to inspect."),
) -> None:
    """Show details of a channel profile."""
    settings = get_settings()
    channels_dir = settings.data_dir / "channels"

    store = JsonDirectoryStore[ChannelProfile](channels_dir, ChannelProfile)
    try:
        ch = store.get(channel_id)
    except FileNotFoundError:
        error(f"Channel not found: {channel_id}")
        raise typer.Exit(1)

    rows = [
        ("ID", f"[id]{ch.id}[/id]"),
        ("Name", ch.name),
        ("Niche", ch.niche or "[dim]not set[/dim]"),
        ("Audience", ch.target_audience or "[dim]not set[/dim]"),
        ("Tone", ch.tone),
        ("Visual Style", ch.visual_style),
        ("Voice", ch.voice_profile),
        ("Duration", ch.default_duration),
        ("Privacy", ch.default_privacy),
    ]
    if ch.content_pillars:
        rows.append(("Pillars", ", ".join(ch.content_pillars)))
    if ch.outro_template:
        rows.append(("Outro", ch.outro_template[:80]))

    console.print()
    console.print(result_panel("Channel Profile", rows))
    console.print()
