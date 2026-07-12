from __future__ import annotations

import logging
import time

from app.domain.generation import GenerationResult
from app.domain.jobs import JobRepository, JobStatus
from app.engines.registry import EngineRegistry
from app.queue.contracts import QueuedJob


logger = logging.getLogger("forge3d.jobs")


class JobExecutor:
    def __init__(self, jobs: JobRepository, engines: EngineRegistry) -> None:
        self.jobs = jobs
        self.engines = engines

    def _log_state(
        self,
        task: QueuedJob,
        status: JobStatus,
        *,
        duration: float = 0.0,
        error: str = "",
    ) -> None:
        logger.info(
            "job_state_changed job_id=%s engine=%s status=%s duration=%.3f error=%s",
            str(task.job.id),
            task.job.engine,
            status.value,
            duration,
            error or "none",
            extra={
                "job_id": str(task.job.id),
                "engine": task.job.engine,
                "job_status": status.value,
                "duration_seconds": round(duration, 3),
                "job_error": error,
            },
        )

    def execute(self, task: QueuedJob) -> GenerationResult:
        job = self.jobs.get(task.job.id) or task.job
        job = self.jobs.save(job.transition(JobStatus.PROCESSING))
        self._log_state(task, JobStatus.PROCESSING)
        started = time.monotonic()
        try:
            engine = self.engines.get(job.engine)
            result = engine.generate(task.context, task.image_path)
            duration = time.monotonic() - started
            self.jobs.save(
                job.transition(
                    JobStatus.COMPLETED,
                    artifact_relative_path=result.artifact_relative_path,
                    metadata=result.metadata,
                )
            )
            self._log_state(task, JobStatus.COMPLETED, duration=duration)
            return result
        except Exception as error:
            duration = time.monotonic() - started
            normalized_error = f"{type(error).__name__}: {error}"
            self.jobs.save(
                job.transition(JobStatus.FAILED, error=normalized_error)
            )
            self._log_state(
                task,
                JobStatus.FAILED,
                duration=duration,
                error=normalized_error,
            )
            raise
