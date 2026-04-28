"""Pipeline orchestrator — runs stages in order with persistence and resume."""

from __future__ import annotations

import logging
import time
from typing import Callable

from ytauto.config.settings import Settings, get_settings
from ytauto.models.job import Job, JobStatus, PipelineStep, StepStatus
from ytauto.pipeline.context import PipelineContext
from ytauto.pipeline.stages import STAGE_REGISTRY
from ytauto.store.json_store import JsonDirectoryStore

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""

    def __init__(self, stage: str, original: Exception) -> None:
        self.stage = stage
        self.original = original
        super().__init__(f"Pipeline failed at stage '{stage}': {original}")


class PipelineOrchestrator:
    """Runs the video-generation pipeline stages sequentially.

    Features:
    * Ordered execution of registered stages.
    * Resume from a specific stage (skip earlier completed stages).
    * Context serialisation after each stage for crash recovery.
    * Job JSON updates for progress tracking.
    """

    def __init__(
        self,
        stages: list[tuple[str, Callable]] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.stages = stages or list(STAGE_REGISTRY)
        self.settings = settings or get_settings()

    def run(
        self,
        context: PipelineContext,
        *,
        job_store: JsonDirectoryStore[Job] | None = None,
        start_from: str | None = None,
        on_stage_start: Callable[[str, int, int], None] | None = None,
        on_stage_done: Callable[[str, int, int, float], None] | None = None,
    ) -> PipelineContext:
        """Execute pipeline stages on *context*.

        Args:
            context: The mutable pipeline context.
            job_store: Optional store for persisting Job updates.
            start_from: If given, skip stages before this one (resume).
            on_stage_start: Callback(stage_name, index, total) before each stage.
            on_stage_done: Callback(stage_name, index, total, elapsed_secs) after each stage.

        Returns:
            The context after all stages have completed.

        Raises:
            PipelineError: On any stage failure (context is saved first).
        """
        total = len(self.stages)
        skipping = start_from is not None

        job = self._load_job(context.job_id, job_store)
        if job:
            job.status = JobStatus.running
            job.touch()
            self._save_job(job, job_store)

        for idx, (name, stage_fn) in enumerate(self.stages, 1):
            if skipping:
                if name == start_from:
                    skipping = False
                else:
                    continue

            context.current_stage = name

            if on_stage_start:
                on_stage_start(name, idx, total)

            self._update_step(job, name, StepStatus.running)
            self._save_job(job, job_store)

            t0 = time.monotonic()
            try:
                stage_fn(context, self.settings)
            except Exception as exc:
                logger.error("Stage '%s' failed: %s", name, exc, exc_info=True)
                context.save()
                self._update_step(job, name, StepStatus.failed, error=str(exc))
                if job:
                    job.status = JobStatus.failed
                    job.error = f"Failed at stage '{name}': {exc}"
                    job.touch()
                self._save_job(job, job_store)
                raise PipelineError(name, exc) from exc

            elapsed = time.monotonic() - t0
            context.completed_stages.append(name)
            self._update_step(job, name, StepStatus.completed)
            context.save()

            if on_stage_done:
                on_stage_done(name, idx, total, elapsed)

        # All stages done
        if job:
            job.status = JobStatus.completed
            job.touch()
            self._save_job(job, job_store)

        return context

    def _load_job(
        self, job_id: str, store: JsonDirectoryStore[Job] | None
    ) -> Job | None:
        if not store:
            return None
        try:
            return store.get(job_id)
        except FileNotFoundError:
            return None

    def _save_job(self, job: Job | None, store: JsonDirectoryStore[Job] | None) -> None:
        if job and store:
            store.save(job)

    def _update_step(
        self,
        job: Job | None,
        stage_name: str,
        status: StepStatus,
        error: str | None = None,
    ) -> None:
        if not job:
            return
        for s in job.steps:
            if s.name == stage_name:
                s.status = status
                if error:
                    s.error = error
                if status == StepStatus.running:
                    from datetime import datetime, timezone
                    s.started_at = datetime.now(timezone.utc)
                elif status in (StepStatus.completed, StepStatus.failed):
                    from datetime import datetime, timezone
                    s.completed_at = datetime.now(timezone.utc)
                break
        job.current_stage = stage_name
