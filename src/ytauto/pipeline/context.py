"""Pipeline context — mutable state that flows through stages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineContext:
    """Mutable state passed through every pipeline stage."""

    job_id: str
    topic: str
    work_dir: Path
    duration: str = "medium"
    voice: str = "onyx"
    engine: str = "claude"
    channel_id: str | None = None
    channel_context: str | None = None
    music_path: Path | None = None

    # Effect options
    transition: str = "crossfade"
    ken_burns: bool = True
    caption_style: str | None = None
    grain_path: Path | None = None

    # Skip flags
    skip_seo: bool = False
    skip_thumbnail: bool = False
    skip_visuals: bool = False

    # Accumulated outputs
    word_timestamps: list[dict] | None = None
    script: dict | None = None
    seo_metadata: dict | None = None
    voiceover_path: Path | None = None
    voiceover_duration: float | None = None
    media_paths: list[Path] = field(default_factory=list)
    thumbnail_path: Path | None = None
    final_video_path: Path | None = None

    # Stage tracking
    current_stage: str = ""
    completed_stages: list[str] = field(default_factory=list)

    def save(self) -> Path:
        """Serialize context to disk for crash recovery."""
        path = self.work_dir / "pipeline_context.json"
        data = {
            "job_id": self.job_id,
            "topic": self.topic,
            "work_dir": str(self.work_dir),
            "duration": self.duration,
            "voice": self.voice,
            "engine": self.engine,
            "script": self.script,
            "seo_metadata": self.seo_metadata,
            "voiceover_path": str(self.voiceover_path) if self.voiceover_path else None,
            "voiceover_duration": self.voiceover_duration,
            "media_paths": [str(p) for p in self.media_paths],
            "thumbnail_path": str(self.thumbnail_path) if self.thumbnail_path else None,
            "final_video_path": str(self.final_video_path) if self.final_video_path else None,
            "current_stage": self.current_stage,
            "completed_stages": self.completed_stages,
        }
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    @classmethod
    def load(cls, work_dir: Path) -> PipelineContext:
        """Restore context from a previous run."""
        path = work_dir / "pipeline_context.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        ctx = cls(
            job_id=data["job_id"],
            topic=data["topic"],
            work_dir=Path(data["work_dir"]),
            duration=data.get("duration", "medium"),
            voice=data.get("voice", "onyx"),
            engine=data.get("engine", "claude"),
        )
        ctx.script = data.get("script")
        ctx.seo_metadata = data.get("seo_metadata")
        vp = data.get("voiceover_path")
        ctx.voiceover_path = Path(vp) if vp else None
        ctx.voiceover_duration = data.get("voiceover_duration")
        ctx.media_paths = [Path(p) for p in data.get("media_paths", [])]
        tp = data.get("thumbnail_path")
        ctx.thumbnail_path = Path(tp) if tp else None
        fp = data.get("final_video_path")
        ctx.final_video_path = Path(fp) if fp else None
        ctx.current_stage = data.get("current_stage", "")
        ctx.completed_stages = data.get("completed_stages", [])
        return ctx
