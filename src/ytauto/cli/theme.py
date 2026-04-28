"""ytauto CLI design system — branded colors, panels, tables, progress bars.

Adapted from the AIVIDIO design system. Provides a consistent, premium visual
language inspired by modern CLIs (Vercel, Stripe, Railway).
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Brand colors — electric blue / cyan gradient
# ---------------------------------------------------------------------------

ACCENT = "#00d4ff"
ACCENT_DIM = "#0099bb"
HIGHLIGHT = "bright_cyan"
SUCCESS = "bright_green"
ERROR = "#ff5555"
WARN = "#f1c40f"
MUTED = "dim"

_THEME = Theme(
    {
        "accent": f"bold {ACCENT}",
        "accent.dim": ACCENT_DIM,
        "highlight": HIGHLIGHT,
        "success": f"bold {SUCCESS}",
        "error": f"bold {ERROR}",
        "warn": f"bold {WARN}",
        "muted": "dim",
        "label": "bold white",
        "value": "bright_white",
        "url": f"underline {ACCENT}",
        "path": "dim italic",
        "id": "dim cyan",
        "status.running": "bold bright_blue",
        "status.done": f"bold {SUCCESS}",
        "status.fail": f"bold {ERROR}",
        "status.pending": "bold yellow",
        "status.created": "bold bright_blue",
    }
)

# ---------------------------------------------------------------------------
# Console instances
# ---------------------------------------------------------------------------

console = Console(theme=_THEME)
err = Console(stderr=True, theme=_THEME)

# ---------------------------------------------------------------------------
# ASCII logo
# ---------------------------------------------------------------------------

LOGO = r"""[bold #00d4ff]
 ╦ ╦╔╦╗  ╔═╗╦ ╦╔╦╗╔═╗
 ╚╦╝ ║   ╠═╣║ ║ ║ ║ ║
  ╩  ╩   ╩ ╩╚═╝ ╩ ╚═╝[/bold #00d4ff]"""

LOGO_COMPACT = "[bold #00d4ff]ytauto[/bold #00d4ff]"

TAGLINE = "[dim]AI-powered YouTube video creation from a single prompt[/dim]"

VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Branded output helpers
# ---------------------------------------------------------------------------


def brand(text: str = "") -> str:
    return f"[accent]{text or 'ytauto'}[/accent]"


def header(title: str, subtitle: str = "", *, border_style: str = ACCENT) -> Panel:
    content = f"[bold bright_white]{title}[/bold bright_white]"
    if subtitle:
        content += f"\n[dim]{subtitle}[/dim]"
    return Panel.fit(content, border_style=border_style, padding=(0, 2))


def result_panel(
    title: str,
    rows: list[tuple[str, str]],
    *,
    border_style: str = ACCENT,
    status: str = "success",
) -> Panel:
    icons = {
        "success": "[success]\u2713[/success]",
        "error": "[error]\u2717[/error]",
        "warning": "[warn]\u26a0[/warn]",
    }
    icon = icons.get(status, "")
    lines: list[str] = [f"{icon} [bold bright_white]{title}[/bold bright_white]\n"]
    max_label = max((len(lbl) for lbl, _ in rows), default=0) + 1
    for label, value in rows:
        lines.append(f"  [label]{label:<{max_label}}[/label] {value}")
    return Panel.fit("\n".join(lines), border_style=border_style, padding=(0, 2))


def success(msg: str) -> None:
    console.print(f"  [success]\u2713[/success] {msg}")


def error(msg: str) -> None:
    err.print(f"  [error]\u2717[/error] {msg}")


def warning(msg: str) -> None:
    console.print(f"  [warn]\u26a0[/warn] {msg}")


def info(msg: str) -> None:
    console.print(f"  [accent]\u2022[/accent] {msg}")


def step(number: int, text: str) -> None:
    console.print(f"\n  [accent]Step {number}[/accent]  {text}")


def divider(char: str = "\u2500", style: str = "dim") -> None:
    console.print(f"[{style}]{char * 60}[/{style}]")


def kv(label: str, value: str, indent: int = 2) -> None:
    pad = " " * indent
    console.print(f"{pad}[label]{label}[/label]  {value}")


def status_badge(status_str: str) -> str:
    mapping = {
        "completed": "[status.done]\u25cf completed[/status.done]",
        "running": "[status.running]\u25cf running[/status.running]",
        "pending": "[status.pending]\u25cf pending[/status.pending]",
        "created": "[status.created]\u25cf created[/status.created]",
        "failed": "[status.fail]\u25cf failed[/status.fail]",
        "cancelled": "[muted]\u25cf cancelled[/muted]",
        "skipped": "[muted]\u25cf skipped[/muted]",
    }
    return mapping.get(status_str.lower().strip(), f"[muted]\u25cf {status_str}[/muted]")


def styled_table(
    title: str = "",
    *,
    show_lines: bool = False,
    border_style: str = ACCENT_DIM,
) -> Table:
    return Table(
        title=f"[bold bright_white]{title}[/bold bright_white]" if title else None,
        show_lines=show_lines,
        border_style=border_style,
        title_style="",
        header_style=f"bold {ACCENT}",
        pad_edge=True,
        row_styles=["", "dim"],
    )


def pipeline_progress():
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    return Progress(
        SpinnerColumn("dots", style=f"bold {ACCENT}"),
        TextColumn("[bold bright_white]{task.description}[/bold bright_white]"),
        BarColumn(bar_width=30, complete_style=ACCENT, finished_style=SUCCESS),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def spinner(text: str = "Processing..."):
    return console.status(f"[accent]{text}[/accent]", spinner="dots")
