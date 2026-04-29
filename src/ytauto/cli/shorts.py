"""Shorts command — Infinite Wealth Lab format.

Black canvas, title at top with colored keywords, landscape clip centered
in the middle (not cropped), sentence-level subtitles of what's being said,
original show audio. No AI voiceover.
"""

from __future__ import annotations

import json
import random
import subprocess
import time
from pathlib import Path

import typer
from rich.live import Live
from rich.table import Table

from ytauto.cli.theme import (
    ACCENT, ACCENT_DIM, SUCCESS, ERROR,
    console, error, header, result_panel, success,
)
from ytauto.config.settings import get_settings
from ytauto.models.job import Job, PipelineStep
from ytauto.store.json_store import JsonDirectoryStore

STAGES = ["select_clips", "transcribe", "compose", "done"]

LABELS = {
    "select_clips": ("Selecting clips", "Picking clips with audio from library..."),
    "transcribe": ("Transcribing", "Whisper \u2192 what's being said in the audio..."),
    "compose": ("Compositing", "Black canvas + title + clip + subtitles..."),
    "done": ("Finishing", ""),
}


def _tbl(stages, done, cur, fail, times):
    t = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
    t.add_column(width=3); t.add_column(min_width=30); t.add_column(width=8, justify="right")
    for n in stages:
        lb, dt = LABELS.get(n, (n, ""))
        if n in done:
            t.add_row(f"[bold {SUCCESS}]\u2713[/]", f"[dim]{lb}[/]", f"[dim]{times.get(n,0):.1f}s[/]")
        elif n == fail:
            t.add_row(f"[bold {ERROR}]\u2717[/]", f"[bold {ERROR}]{lb}[/]", "")
        elif n == cur:
            t.add_row(f"[bold {ACCENT}]\u25b8[/]", f"[bold bright_white]{lb}[/]  [{ACCENT_DIM}]{dt}[/]", f"[{ACCENT}]...[/]")
        else:
            t.add_row("[dim]\u2022[/]", f"[dim]{lb}[/]", "")
    return t


def shorts(
    title: str = typer.Argument(None, help="Title shown at top of the Short (with colored keywords)."),
    seconds: int = typer.Option(50, "--seconds", "-s", help="Target duration (30-60)."),
    clips_source: str = typer.Option("library", "--clips", help="'library' or path to folder."),
    clip_tag: str = typer.Option(None, "--clip-tag", help="Filter clips by tag."),
    highlight: str = typer.Option("", "--highlight", "-h", help="Comma-separated words to color in the title."),
    num_clips: int = typer.Option(4, "--num-clips", "-n", help="Number of clips (2-8)."),
    open_after: bool = typer.Option(False, "--open", help="Open after creation."),
) -> None:
    """Create a YouTube Short in the Infinite Wealth Lab format.

    Black canvas with colored title at top, landscape show footage centered
    in the middle (not cropped), subtitles of what's being said at bottom.
    Original show audio plays — no AI voiceover.
    """
    settings = get_settings()
    settings.ensure_directories()
    seconds = max(30, min(60, seconds))
    num_clips = max(2, min(8, num_clips))

    if not title:
        console.print()
        console.print(header("New YouTube Short", "Title shown at top of the video:"))
        console.print()
        title = typer.prompt("  Title")
        if not title.strip():
            title = "Untitled Short"
        console.print()

    hl_words = [w.strip() for w in highlight.split(",") if w.strip()] if highlight else []
    src_label = f"Library (tag: {clip_tag})" if clip_tag else "Library"

    job = Job(topic=title, duration_config=f"{seconds}s")
    work = settings.workspaces_dir / job.id
    work.mkdir(parents=True, exist_ok=True)
    job.workspace_dir = str(work)
    job.steps = [PipelineStep(name=n) for n in STAGES]
    store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    store.save(job)

    console.print()
    console.print(header(
        "Creating YouTube Short",
        f'"{title}"\n~{seconds}s  \u2502  Clips: {src_label}  \u2502  Original audio: \u2713\nJob: {job.id}',
    ))
    console.print()

    done: set[str] = set()
    times: dict[str, float] = {}
    cur = None
    clips: list[Path] = []
    wts: list[dict] = []
    final: Path | None = None

    try:
        with Live(_tbl(STAGES, done, None, None, times), console=console, refresh_per_second=4) as live:

            def _run(name, fn):
                nonlocal cur
                cur = name
                live.update(_tbl(STAGES, done, cur, None, times))
                t0 = time.monotonic()
                fn()
                done.add(name)
                times[name] = time.monotonic() - t0
                live.update(_tbl(STAGES, done, None, None, times))

            # ── 1. Select clips with audio ───────────────────────────────
            def do_select():
                nonlocal clips
                if clips_source == "library":
                    from ytauto.services.clips import get_clips_dir, list_clips
                    all_c = list_clips(tag=clip_tag)
                    if not all_c:
                        raise RuntimeError("No clips in library. Run: ytauto clips-rip <url>")
                    cdir = get_clips_dir()
                    with_audio = []
                    for c in all_c:
                        p = cdir / c["file"]
                        if not p.exists():
                            continue
                        r = subprocess.run(
                            ["ffprobe", "-v", "error", "-select_streams", "a",
                             "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(p)],
                            capture_output=True, text=True)
                        if r.stdout.strip():
                            with_audio.append(p)
                    if not with_audio:
                        raise RuntimeError("No clips with audio. Re-rip with --keep-audio")
                    random.shuffle(with_audio)
                    clips = [with_audio[i % len(with_audio)] for i in range(num_clips)]
                else:
                    folder = Path(clips_source).expanduser().resolve()
                    exts = {".mp4", ".mov", ".mkv", ".webm"}
                    vids = [f for f in folder.iterdir() if f.suffix.lower() in exts]
                    random.shuffle(vids)
                    clips = [vids[i % len(vids)] for i in range(num_clips)]

            _run("select_clips", do_select)

            # ── 2. Transcribe audio with Whisper ─────────────────────────
            def do_transcribe():
                nonlocal wts
                # Concat clip audio for transcription
                per_clip = seconds / len(clips)
                audio_parts = []
                for i, cp in enumerate(clips):
                    seg = work / f"_aseg_{i}.aac"
                    dur = _dur(cp)
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(cp),
                        "-t", str(min(per_clip, dur)),
                        "-vn", "-c:a", "aac", "-b:a", "128k", str(seg),
                    ], capture_output=True)
                    if seg.exists():
                        audio_parts.append(seg)

                if not audio_parts:
                    return

                # Concat
                alist = work / "_alist.txt"
                alist.write_text("\n".join(f"file '{p}'" for p in audio_parts), encoding="utf-8")
                afull = work / "_audio.mp3"
                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(alist),
                    "-c:a", "libmp3lame", "-b:a", "128k", str(afull),
                ], capture_output=True)

                # Whisper
                import openai
                if settings.has_openai() and afull.exists():
                    client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())
                    with open(afull, "rb") as f:
                        tx = client.audio.transcriptions.create(
                            model="whisper-1", file=f,
                            response_format="verbose_json",
                            timestamp_granularities=["word"],
                        )
                    for w in getattr(tx, "words", []):
                        wts.append({"word": w.word.strip(), "start": w.start, "end": w.end})

                (work / "word_timestamps.json").write_text(json.dumps(wts, indent=2), encoding="utf-8")

                # Cleanup
                for p in audio_parts:
                    p.unlink(missing_ok=True)
                alist.unlink(missing_ok=True)
                afull.unlink(missing_ok=True)

            _run("transcribe", do_transcribe)

            # ── 3. Compose the full IWL-style frame ──────────────────────
            def do_compose():
                nonlocal final
                from ytauto.video.shorts_composer import compose_short
                slug = title.replace(" ", "_")[:40]
                final = work / f"{slug}_short.mp4"
                compose_short(
                    clip_paths=clips,
                    title=title,
                    word_timestamps=wts,
                    output_path=final,
                    highlight_words=hl_words,
                    target_seconds=seconds,
                )

            _run("compose", do_compose)

            # ── 4. Done ──────────────────────────────────────────────────
            def do_done():
                job.video_path = str(final) if final else ""
                job.status = "completed"
                job.touch()
                store.save(job)

            _run("done", do_done)

    except Exception as exc:
        console.print(_tbl(STAGES, done, None, cur, times))
        console.print()
        error(f"Failed: {exc}")
        console.print(f"\n  [dim]Job: {job.id}[/dim]\n")
        raise typer.Exit(1)

    rows = [
        ("Job ID", f"[id]{job.id}[/id]"),
        ("Format", "IWL-style (black canvas + title + clip + subtitles)"),
        ("Audio", "Original show audio"),
        ("Source", src_label),
    ]
    if final and final.exists():
        sz = final.stat().st_size / (1024 * 1024)
        rows.append(("Video", f"[path]{final}[/path]"))
        rows.append(("Size", f"{sz:.1f} MB"))
        rows.append(("Duration", f"{int(_dur(final))}s"))
    rows.append(("Words", str(len(wts))))
    rows.append(("Pipeline", f"{sum(times.values()):.0f}s"))

    console.print()
    console.print(result_panel("Short Created", rows))
    console.print()
    success("Your YouTube Short is ready!")
    console.print(f"  [dim]Open:[/dim]   [accent]ytauto open {job.id}[/accent]")
    console.print(f"  [dim]Upload:[/dim] [accent]ytauto upload {job.id}[/accent]\n")

    if open_after and final and final.exists():
        import platform
        if platform.system() == "Darwin":
            subprocess.Popen(["open", str(final)])


def _dur(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())
