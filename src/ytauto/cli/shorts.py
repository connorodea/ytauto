"""Shorts command — real footage + original audio + captions of what's being said.

Replicates Infinite Wealth Lab format:
- Real movie/TV clips with ORIGINAL AUDIO (Harvey Specter speaking)
- Scaled to fill 9:16 vertical (no chopping — pillarbox/letterbox if needed)
- Bold captions showing WHAT IS BEING SAID (Whisper transcription)
- No AI voiceover
"""

from __future__ import annotations

import json
import random
import subprocess
import shutil
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

SHORTS_STAGES = [
    "select_clips",
    "assemble",
    "transcribe",
    "burn_captions",
    "done",
]

STAGE_LABELS = {
    "select_clips": ("Selecting clips", "Picking clips from your library..."),
    "assemble": ("Assembling", "9:16 scale + concat with original audio..."),
    "transcribe": ("Transcribing", "Whisper \u2192 what\u2019s being said..."),
    "burn_captions": ("Burning captions", "Bold word-by-word captions via Pillow..."),
    "done": ("Finishing", ""),
}


def _stage_table(stages, completed, current, failed, timings):
    t = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
    t.add_column("i", width=3)
    t.add_column("s", min_width=30)
    t.add_column("t", width=8, justify="right")
    for name in stages:
        lb, dt = STAGE_LABELS.get(name, (name, ""))
        if name in completed:
            t.add_row(f"[bold {SUCCESS}]\u2713[/bold {SUCCESS}]", f"[dim]{lb}[/dim]", f"[dim]{timings.get(name,0):.1f}s[/dim]")
        elif name == failed:
            t.add_row(f"[bold {ERROR}]\u2717[/bold {ERROR}]", f"[bold {ERROR}]{lb}[/bold {ERROR}]", "")
        elif name == current:
            t.add_row(f"[bold {ACCENT}]\u25b8[/bold {ACCENT}]", f"[bold bright_white]{lb}[/bold bright_white]  [{ACCENT_DIM}]{dt}[/{ACCENT_DIM}]", f"[{ACCENT}]...[/{ACCENT}]")
        else:
            t.add_row("[dim]\u2022[/dim]", f"[dim]{lb}[/dim]", "")
    return t


def shorts(
    topic: str = typer.Argument(None, help="Topic label (used for filename only)."),
    seconds: int = typer.Option(45, "--seconds", "-s", help="Target duration (30-60)."),
    clips_source: str = typer.Option("library", "--clips", help="'library' or path to folder."),
    clip_tag: str = typer.Option(None, "--clip-tag", help="Filter clips by tag (e.g. 'suits')."),
    captions_style: str = typer.Option("hormozi", "--captions", "-c", help="Caption style: hormozi, mrbeast, tiktok, cinematic, minimal."),
    num_clips: int = typer.Option(4, "--num-clips", "-n", help="Number of clips (2-8)."),
    open_after: bool = typer.Option(False, "--open", help="Open after creation."),
) -> None:
    """Create a YouTube Short with real footage, original audio, and captions.

    Picks clips from your library, keeps the ORIGINAL show audio,
    transcribes what's being said with Whisper, and burns bold captions on top.
    """
    settings = get_settings()
    settings.ensure_directories()
    seconds = max(30, min(60, seconds))
    num_clips = max(2, min(8, num_clips))

    if not topic:
        console.print()
        console.print(header("New YouTube Short", "Label for this Short (just for the filename):"))
        console.print()
        topic = typer.prompt("  Label")
        if not topic.strip():
            topic = "short"
        console.print()

    src_label = f"Clip Library (tag: {clip_tag})" if clip_tag else "Clip Library" if clips_source == "library" else clips_source

    job = Job(topic=topic, duration_config=f"{seconds}s")
    work_dir = settings.workspaces_dir / job.id
    work_dir.mkdir(parents=True, exist_ok=True)
    job.workspace_dir = str(work_dir)
    job.steps = [PipelineStep(name=n) for n in SHORTS_STAGES]
    job_store = JsonDirectoryStore[Job](settings.jobs_dir, Job)
    job_store.save(job)

    console.print()
    console.print(header(
        "Creating YouTube Short",
        f'"{topic}"\n~{seconds}s  \u2502  Clips: {src_label}  \u2502  Captions: {captions_style}\nOriginal audio: \u2713  \u2502  Job: {job.id}',
    ))
    console.print()

    done: set[str] = set()
    times: dict[str, float] = {}
    cur: str | None = None
    clip_paths: list[Path] = []
    final_path: Path | None = None
    word_ts: list[dict] = []

    try:
        with Live(_stage_table(SHORTS_STAGES, done, None, None, times), console=console, refresh_per_second=4) as live:

            def _run(name, fn):
                nonlocal cur
                cur = name
                live.update(_stage_table(SHORTS_STAGES, done, cur, None, times))
                t0 = time.monotonic()
                fn()
                done.add(name)
                times[name] = time.monotonic() - t0
                live.update(_stage_table(SHORTS_STAGES, done, None, None, times))

            # ── 1. Select clips (prefer clips WITH audio) ────────────────
            def do_select():
                nonlocal clip_paths
                if clips_source == "library":
                    from ytauto.services.clips import get_clips_dir, list_clips
                    all_clips = list_clips(tag=clip_tag)
                    if not all_clips:
                        raise RuntimeError("No clips in library. Run: ytauto clips-rip <url>")

                    clips_dir = get_clips_dir()
                    # Filter to clips that have audio
                    with_audio = []
                    for c in all_clips:
                        p = clips_dir / c["file"]
                        if not p.exists():
                            continue
                        probe = subprocess.run(
                            ["ffprobe", "-v", "error", "-select_streams", "a",
                             "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(p)],
                            capture_output=True, text=True,
                        )
                        if probe.stdout.strip():
                            with_audio.append(p)
                    if not with_audio:
                        raise RuntimeError(
                            "No clips with audio found. Re-rip with: "
                            "ytauto clips-rip <url> --keep-audio --tags suits"
                        )
                    random.shuffle(with_audio)
                    clip_paths = [with_audio[i % len(with_audio)] for i in range(num_clips)]
                else:
                    folder = Path(clips_source).expanduser().resolve()
                    exts = {".mp4", ".mov", ".mkv", ".webm"}
                    vids = [f for f in folder.iterdir() if f.suffix.lower() in exts]
                    random.shuffle(vids)
                    clip_paths = [vids[i % len(vids)] for i in range(num_clips)]

            _run("select_clips", do_select)

            # ── 2. Scale to 9:16 + concat WITH audio ────────────────────
            def do_assemble():
                nonlocal final_path

                target_per = seconds / len(clip_paths)
                scaled: list[Path] = []

                for i, clip in enumerate(clip_paths):
                    out = work_dir / f"_sc_{i:03d}.mp4"
                    dur = _get_dur(clip)
                    trim = min(target_per, dur)
                    # Scale to FIT inside 1080x1920 (letterbox, don't crop)
                    _scale_to_vertical(clip, out, trim)
                    scaled.append(out)

                # Concat — re-encode both streams to guarantee compatibility
                cf = work_dir / "_list.txt"
                cf.write_text("\n".join(f"file '{p}'" for p in scaled), encoding="utf-8")
                joined = work_dir / "_joined.mp4"
                r = subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(cf),
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    str(joined),
                ], capture_output=True, text=True)
                if r.returncode != 0:
                    raise RuntimeError(f"Concat failed: {r.stderr[-400:]}")

                final_path = joined
                for f in scaled:
                    f.unlink(missing_ok=True)
                cf.unlink(missing_ok=True)

            _run("assemble", do_assemble)

            # ── 3. Transcribe the actual audio with Whisper ──────────────
            def do_transcribe():
                nonlocal word_ts
                # Extract audio from the assembled video
                audio_tmp = work_dir / "_audio.mp3"
                r = subprocess.run([
                    "ffmpeg", "-y", "-i", str(final_path),
                    "-vn", "-c:a", "libmp3lame", "-b:a", "128k",
                    str(audio_tmp),
                ], capture_output=True, text=True)

                if r.returncode != 0 or not audio_tmp.exists():
                    # No audio track — skip transcription
                    return

                # Whisper via OpenAI API
                import openai
                if settings.has_openai():
                    client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())
                    with open(audio_tmp, "rb") as f:
                        transcript = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=f,
                            response_format="verbose_json",
                            timestamp_granularities=["word"],
                        )
                    for w in getattr(transcript, "words", []):
                        word_ts.append({"word": w.word.strip(), "start": w.start, "end": w.end})

                (work_dir / "word_timestamps.json").write_text(
                    json.dumps(word_ts, indent=2), encoding="utf-8",
                )
                audio_tmp.unlink(missing_ok=True)

            _run("transcribe", do_transcribe)

            # ── 4. Burn captions (what's being said) ─────────────────────
            def do_burn():
                nonlocal final_path
                if not word_ts or not final_path:
                    return

                from ytauto.video.pillow_captions import burn_pillow_captions
                output = work_dir / "_captioned.mp4"
                burn_pillow_captions(
                    video_path=final_path,
                    word_timestamps=word_ts,
                    output_path=output,
                    width=1080, height=1920, fps=30,
                    style=captions_style,
                )
                final_path.unlink(missing_ok=True)
                final_path = output

            _run("burn_captions", do_burn)

            # ── 5. Done ──────────────────────────────────────────────────
            def do_done():
                nonlocal final_path
                slug = topic.replace(" ", "_")[:40]
                dest = work_dir / f"{slug}_short.mp4"
                if final_path and final_path.exists() and final_path != dest:
                    shutil.move(str(final_path), str(dest))
                    final_path = dest
                job.video_path = str(final_path) if final_path else ""
                job.status = "completed"
                job.touch()
                job_store.save(job)

            _run("done", do_done)

    except Exception as exc:
        console.print(_stage_table(SHORTS_STAGES, done, None, cur, times))
        console.print()
        error(f"Failed: {exc}")
        console.print(f"\n  [dim]Job: {job.id}[/dim]\n")
        raise typer.Exit(1)

    rows = [
        ("Job ID", f"[id]{job.id}[/id]"),
        ("Format", "9:16 Vertical (1080x1920)"),
        ("Audio", "Original show audio"),
        ("Captions", f"Whisper transcription \u2192 {captions_style} style"),
        ("Source", src_label),
    ]
    if final_path and final_path.exists():
        sz = final_path.stat().st_size / (1024 * 1024)
        rows.append(("Video", f"[path]{final_path}[/path]"))
        rows.append(("Size", f"{sz:.1f} MB"))
        rows.append(("Duration", f"{int(_get_dur(final_path))}s"))
    rows.append(("Clips", str(len(clip_paths))))
    rows.append(("Words", str(len(word_ts))))
    rows.append(("Pipeline", f"{sum(times.values()):.0f}s"))

    console.print()
    console.print(result_panel("Short Created", rows))
    console.print()
    success("Your YouTube Short is ready!")
    console.print(f"  [dim]Open:[/dim]   [accent]ytauto open {job.id}[/accent]")
    console.print(f"  [dim]Upload:[/dim] [accent]ytauto upload {job.id}[/accent]\n")

    if open_after and final_path and final_path.exists():
        import platform
        if platform.system() == "Darwin":
            subprocess.Popen(["open", str(final_path)])


def _scale_to_vertical(inp: Path, out: Path, duration: float) -> Path:
    """Scale video to fit 1080x1920 (9:16) without cropping.

    Scales up to fill the frame, adds black bars only if aspect ratio
    is too wide. Keeps original audio.
    """
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "setsar=1"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(inp),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Scale failed: {r.stderr[-400:]}")
    return out


def _get_dur(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())
