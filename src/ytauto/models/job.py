"""Job and pipeline step models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _job_id() -> str:
    return f"job_{uuid.uuid4().hex[:10]}"


class JobStatus(str, Enum):
    created = "created"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class StepStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    skipped = "skipped"
    failed = "failed"


class PipelineStep(BaseModel):
    name: str
    status: StepStatus = StepStatus.pending
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    outputs: list[str] = Field(default_factory=list)


class VideoMetadata(BaseModel):
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    category_id: str = "22"
    privacy: str = "private"


class Job(BaseModel):
    id: str = Field(default_factory=_job_id)
    topic: str
    status: JobStatus = JobStatus.created
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    workspace_dir: str = ""
    steps: list[PipelineStep] = Field(default_factory=list)

    # Pipeline outputs
    script_path: str | None = None
    voiceover_path: str | None = None
    video_path: str | None = None
    thumbnail_path: str | None = None
    youtube_url: str | None = None
    metadata: VideoMetadata = Field(default_factory=VideoMetadata)

    # Config used for this job
    duration_config: str = "medium"
    voice_config: str = "onyx"
    engine_config: str = "claude"

    # Error tracking
    error: str | None = None
    current_stage: str | None = None

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = _utc_now()
