"""Script-only generation command."""

from __future__ import annotations

import json

import typer

from ytauto.cli.theme import console, error, header, result_panel, spinner, success
from ytauto.config.settings import get_settings


def script(
    topic: str = typer.Argument(help="The video topic."),
    duration: str = typer.Option(
        "medium", "--duration", "-d",
        help="Video length: short (~5m), medium (~10m), long (~18m).",
    ),
    engine: str = typer.Option(
        None, "--engine", "-e",
        help="LLM engine: claude or openai.",
    ),
    output: str = typer.Option(
        None, "--output", "-o",
        help="Save script to file (default: print to stdout).",
    ),
    raw: bool = typer.Option(
        False, "--json",
        help="Output raw JSON.",
    ),
) -> None:
    """Generate a video script using AI without creating a full job."""
    settings = get_settings()
    engine = engine or settings.default_llm_provider

    console.print()
    console.print(header("Script Generation", f'Topic: "{topic}" | Duration: {duration}'))
    console.print()

    from ytauto.services.scriptgen import generate_script

    try:
        with spinner("Generating script..."):
            result = generate_script(
                topic=topic,
                duration=duration,
                engine=engine,
                settings=settings,
            )
    except Exception as exc:
        error(f"Script generation failed: {exc}")
        raise typer.Exit(1)

    if output:
        from pathlib import Path
        Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        success(f"Script saved to [path]{output}[/path]")
    elif raw:
        console.print_json(json.dumps(result, indent=2))
    else:
        # Pretty print
        title = result.get("title", "Untitled")
        console.print(result_panel(
            "Script Generated",
            [
                ("Title", title),
                ("Sections", str(len(result.get("sections", [])))),
                ("Tags", str(len(result.get("tags", [])))),
            ],
        ))
        console.print()

        console.print(f"  [accent]Hook:[/accent] {result.get('hook', '')[:200]}")
        console.print()

        for i, section in enumerate(result.get("sections", []), 1):
            heading = section.get("heading", f"Section {i}")
            narration = section.get("narration", "")
            console.print(f"  [accent]{i}. {heading}[/accent]")
            console.print(f"  [dim]{narration[:150]}...[/dim]\n")

        console.print(f"  [accent]Outro:[/accent] {result.get('outro', '')[:200]}\n")
