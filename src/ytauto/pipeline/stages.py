"""Pipeline stage functions and registry.

Each stage function has the signature:
    def stage_xxx(ctx: PipelineContext, settings: Settings) -> None

Stages mutate the context and write artifacts to the workspace.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ytauto.config.settings import Settings
    from ytauto.pipeline.context import PipelineContext


def stage_script_generation(ctx: PipelineContext, settings: Settings) -> None:
    """Generate the video script using AI."""
    from ytauto.services.scriptgen import generate_script

    script = generate_script(
        topic=ctx.topic,
        duration=ctx.duration,
        engine=ctx.engine,
        settings=settings,
        channel_context=ctx.channel_context,
    )
    ctx.script = script

    # Save script JSON
    script_path = ctx.work_dir / "script.json"
    script_path.write_text(json.dumps(script, indent=2), encoding="utf-8")

    # Save narration as plain text (hook + sections + outro)
    narration_parts = [script.get("hook", "")]
    for section in script.get("sections", []):
        narration_parts.append(section.get("narration", ""))
    narration_parts.append(script.get("outro", ""))
    narration_text = "\n\n".join(p for p in narration_parts if p)

    narration_path = ctx.work_dir / "narration.txt"
    narration_path.write_text(narration_text, encoding="utf-8")


def stage_seo_generation(ctx: PipelineContext, settings: Settings) -> None:
    """Generate SEO-optimized metadata."""
    from ytauto.services.seogen import generate_seo

    if not ctx.script:
        raise RuntimeError("Script must be generated before SEO metadata.")

    section_headings = [s.get("heading", "") for s in ctx.script.get("sections", [])]

    seo = generate_seo(
        topic=ctx.topic,
        title=ctx.script.get("title", ctx.topic),
        section_headings=section_headings,
        engine=ctx.engine,
        settings=settings,
    )
    ctx.seo_metadata = seo

    seo_path = ctx.work_dir / "seo.json"
    seo_path.write_text(json.dumps(seo, indent=2), encoding="utf-8")


def stage_voiceover(ctx: PipelineContext, settings: Settings) -> None:
    """Generate voiceover audio from the script narration."""
    from ytauto.services.tts import synthesize_voiceover

    narration_path = ctx.work_dir / "narration.txt"
    if not narration_path.exists():
        raise RuntimeError("Narration text not found. Run script generation first.")

    narration_text = narration_path.read_text(encoding="utf-8")
    output_path = ctx.work_dir / "voiceover.mp3"

    synthesize_voiceover(
        text=narration_text,
        output_path=output_path,
        voice=ctx.voice,
        settings=settings,
    )

    ctx.voiceover_path = output_path

    # Get audio duration
    from ytauto.services.ffmpeg import get_audio_duration
    ctx.voiceover_duration = get_audio_duration(output_path)


def stage_captions(ctx: PipelineContext, settings: Settings) -> None:
    """Transcribe voiceover for word-level timestamps (for captions)."""
    if not ctx.caption_style:
        return  # Captions not requested, skip

    if not ctx.voiceover_path or not ctx.voiceover_path.exists():
        raise RuntimeError("Voiceover must exist before caption transcription.")

    from ytauto.video.captions import transcribe_for_timestamps

    timestamps_path = ctx.work_dir / "word_timestamps.json"
    ctx.word_timestamps = transcribe_for_timestamps(
        ctx.voiceover_path, timestamps_path,
    )


def stage_visual_generation(ctx: PipelineContext, settings: Settings) -> None:
    """Generate images for each script section."""
    from ytauto.services.imagegen import generate_images

    if not ctx.script:
        raise RuntimeError("Script must be generated before visuals.")

    media_dir = ctx.work_dir / "media"
    media_dir.mkdir(exist_ok=True)

    sections = ctx.script.get("sections", [])
    paths = generate_images(sections=sections, output_dir=media_dir, settings=settings)
    ctx.media_paths = paths


def stage_thumbnail_generation(ctx: PipelineContext, settings: Settings) -> None:
    """Generate a YouTube thumbnail."""
    from ytauto.services.thumbnailgen import generate_thumbnail

    title = ""
    if ctx.script:
        title = ctx.script.get("title", ctx.topic)
    else:
        title = ctx.topic

    output_path = ctx.work_dir / "thumbnail.png"
    generate_thumbnail(
        title=title,
        topic=ctx.topic,
        output_path=output_path,
        settings=settings,
    )
    ctx.thumbnail_path = output_path


def stage_video_assembly(ctx: PipelineContext, settings: Settings) -> None:
    """Assemble the final video with Ken Burns, transitions, captions, and effects."""
    from ytauto.services.ffmpeg import assemble_video

    if not ctx.voiceover_path or not ctx.voiceover_path.exists():
        raise RuntimeError("Voiceover must be generated before video assembly.")

    if not ctx.media_paths:
        raise RuntimeError("Visuals must be generated before video assembly.")

    media = sorted(ctx.media_paths)
    title = ctx.topic.replace(" ", "_")[:50]
    output_path = ctx.work_dir / f"{title}.mp4"

    # Get section headings for title overlays
    section_headings = None
    if ctx.script:
        section_headings = [s.get("heading", "") for s in ctx.script.get("sections", [])]

    assemble_video(
        image_paths=media,
        voiceover_path=ctx.voiceover_path,
        output_path=output_path,
        settings=settings,
        background_music_path=ctx.music_path,
        transition=ctx.transition,
        ken_burns=ctx.ken_burns,
        section_headings=section_headings,
        caption_style=ctx.caption_style,
        word_timestamps=ctx.word_timestamps,
        grain_path=ctx.grain_path,
    )
    ctx.final_video_path = output_path


def stage_summary(ctx: PipelineContext, settings: Settings) -> None:
    """Final stage — no-op, exists so the orchestrator can mark completion."""
    pass


# ---------------------------------------------------------------------------
# Stage registry — ordered list of (name, callable)
# ---------------------------------------------------------------------------

STAGE_REGISTRY: list[tuple[str, callable]] = [
    ("script_generation", stage_script_generation),
    ("seo_generation", stage_seo_generation),
    ("voiceover", stage_voiceover),
    ("captions", stage_captions),
    ("visual_generation", stage_visual_generation),
    ("thumbnail_generation", stage_thumbnail_generation),
    ("video_assembly", stage_video_assembly),
    ("summary", stage_summary),
]
