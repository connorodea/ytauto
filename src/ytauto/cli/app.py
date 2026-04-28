"""Main Typer application — registers all commands."""

from __future__ import annotations

import typer

from ytauto import __version__
from ytauto.cli.theme import LOGO, TAGLINE, console, ACCENT, header

app = typer.Typer(
    name="ytauto",
    help="AI-powered YouTube video creation from a single prompt.",
    no_args_is_help=False,
    rich_markup_mode="rich",
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"ytauto [accent]{__version__}[/accent]")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """ytauto \u2014 AI-powered YouTube video creation."""
    if ctx.invoked_subcommand is None:
        _interactive_menu()


def _interactive_menu() -> None:
    """Show a branded interactive menu when no command is given."""
    console.print(LOGO)
    console.print(f"  {TAGLINE}")
    console.print(f"  Version [accent]{__version__}[/accent]\n")

    choices = [
        ("1", "Create a new video", "create"),
        ("2", "Generate a script only", "script"),
        ("3", "View all jobs", "jobs"),
        ("4", "Check environment", "doctor"),
        ("5", "Configure API keys", "setup"),
        ("6", "Exit", None),
    ]

    console.print("  [bold bright_white]What would you like to do?[/bold bright_white]\n")
    for key, label, _ in choices:
        console.print(f"    [accent]{key}.[/accent] {label}")
    console.print()

    choice = typer.prompt("  Choice [1-6]", default="1")

    selected = None
    for key, label, cmd in choices:
        if choice == key:
            selected = cmd
            break

    if selected is None:
        console.print("\n  [dim]Goodbye![/dim]\n")
        raise typer.Exit()

    console.print()

    if selected == "create":
        from ytauto.cli.create import create
        ctx = typer.Context(typer.main.get_command(app))
        create(topic=None)
    elif selected == "script":
        topic = typer.prompt("  Topic")
        from ytauto.cli.script import script
        script(topic=topic)
    elif selected == "jobs":
        from ytauto.cli.jobs import jobs
        jobs()
    elif selected == "doctor":
        from ytauto.cli.doctor import doctor
        doctor()
    elif selected == "setup":
        from ytauto.cli.setup import setup
        setup()


# ---------------------------------------------------------------------------
# Register commands
# ---------------------------------------------------------------------------

from ytauto.cli.create import create  # noqa: E402
from ytauto.cli.doctor import doctor  # noqa: E402
from ytauto.cli.jobs import jobs, job, resume  # noqa: E402
from ytauto.cli.script import script  # noqa: E402
from ytauto.cli.setup import setup  # noqa: E402
from ytauto.cli.voiceover import voiceover  # noqa: E402
from ytauto.cli.render import render  # noqa: E402

app.command()(create)
app.command()(doctor)
app.command()(jobs)
app.command()(job)
app.command()(resume)
app.command()(script)
app.command()(setup)
app.command()(voiceover)
app.command()(render)


def run() -> None:
    """Entry point for the CLI."""
    app()
