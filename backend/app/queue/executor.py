from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from app.domain.generation import GenerationResult
from app.domain.jobs import JobRepository, JobStatus
from app.engines.registry import EngineRegistry
from app.queue.contracts import QueuedJob

logger = logging.getLogger("forge3d.jobs")


class JobExecutor:
    def __init__(
        self,
        jobs: JobRepository,
        engines: EngineRegistry,
        metrics=None,
        on_completed: Optional[Callable[[QueuedJob, GenerationResult], None]] = None,
    ) -> None:
        self.jobs = jobs
        self.engines = engines
        self.metrics = metrics
        self.on_completed = on_completed

    def _log_state(
        self,
        task: QueuedJob,
        status: JobStatus,
        *,
        duration: float = 0.0,
        error_code: str = "",
    ) -> None:
        logger.info(
            "job_state_changed job_id=%s engine=%s status=%s duration=%.3f error=%s",
            str(task.job.id),
            task.job.engine,
            status.value,
            duration,
            error_code or "none",
            extra={
                "job_id": str(task.job.id),
                "engine": task.job.engine,
                "job_status": status.value,
                "duration_seconds": round(duration, 3),
                "error_code": error_code,
            },
        )

    def execute(self, task: QueuedJob) -> GenerationResult:
        job = self.jobs.get(task.job.id) or task.job
        job = self.jobs.save(job.transition(JobStatus.PROCESSING))
        self._log_state(task, JobStatus.PROCESSING)
        if self.metrics:
            self.metrics.observe_job(task.job.engine, JobStatus.PROCESSING.value)
        started = time.monotonic()
        try:
            engine = self.engines.get(job.engine)
            result = engine.generate(task.context, task.image_path)
            duration = time.monotonic() - started
            completed = self.jobs.save(
                job.transition(
                    JobStatus.COMPLETED,
                    artifact_relative_path=result.artifact_relative_path,
                    metadata=result.metadata,
                )
            )
            self._log_state(task, JobStatus.COMPLETED, duration=duration)
            if self.metrics:
                self.metrics.observe_job(task.job.engine, "completed", duration)
            if self.on_completed is not None:
                try:
                    self.on_completed(task, result)
                except Exception as error:
                    logger.error(
                        "post_generation_hook_failed job_id=%s engine=%s error_code=%s",
                        completed.id,
                        completed.engine,
                        type(error).__name__,
                        extra={
                            "job_id": str(completed.id),
                            "engine": completed.engine,
                            "error_code": type(error).__name__,
                        },
                    )
            return result
        except Exception as error:
            duration = time.monotonic() - started
            normalized_error = type(error).__name__
            self.jobs.save(job.transition(JobStatus.FAILED, error=normalized_error))
            self._log_state(
                task,
                JobStatus.FAILED,
                duration=duration,
                error_code=normalized_error,
            )
            if self.metrics:
                self.metrics.observe_job(task.job.engine, "failed", duration)
            raise
