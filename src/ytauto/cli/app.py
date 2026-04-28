"""Main Typer application — registers all commands."""

from __future__ import annotations

import typer

from ytauto import __version__
from ytauto.cli.theme import LOGO, TAGLINE, console

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
    """ytauto — AI-powered YouTube video creation."""
    if ctx.invoked_subcommand is None:
        console.print(LOGO)
        console.print(f"  {TAGLINE}")
        console.print(f"  Version [accent]{__version__}[/accent]\n")
        console.print("  [dim]Quick start:[/dim]")
        console.print('    [accent]ytauto create[/accent] "Your video topic here"')
        console.print("    [accent]ytauto doctor[/accent]   — check your setup")
        console.print("    [accent]ytauto setup[/accent]    — configure API keys")
        console.print("    [accent]ytauto --help[/accent]   — all commands\n")


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
