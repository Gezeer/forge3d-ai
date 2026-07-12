from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.domain.jobs import Job, JobRepository, TextureStatus
from app.engines.contracts import JobContext
from app.texture.contracts import TextureRequest, TextureService

logger = logging.getLogger("forge3d.texture")


@dataclass(frozen=True)
class TextureQueuedJob:
    job: Job
    context: JobContext
    mesh_path: Path
    reference_image: Path
    request: TextureRequest


class TextureExecutor:
    def __init__(self, jobs: JobRepository, service: TextureService) -> None:
        self.jobs = jobs
        self.service = service

    def execute(self, task: TextureQueuedJob):
        job = self.jobs.get(task.job.id) or task.job
        job = self.jobs.save(job.transition_texture(TextureStatus.PROCESSING))
        logger.info(
            "texture_state_changed job_id=%s engine=%s status=texturing",
            job.id,
            self.service.name,
            extra={
                "job_id": str(job.id),
                "engine": self.service.name,
                "status": "texturing",
            },
        )
        try:
            result = self.service.texture(
                task.context, task.mesh_path, task.reference_image, task.request
            )
            self.jobs.save(
                job.transition_texture(
                    TextureStatus.COMPLETED,
                    artifact_relative_path=result.artifact_relative_path,
                    metadata=result.metadata,
                )
            )
            return result
        except Exception as error:
            self.jobs.save(
                job.transition_texture(TextureStatus.FAILED, error=type(error).__name__)
            )
            logger.error(
                "texture_state_changed job_id=%s engine=%s status=texture_failed error_code=%s",
                job.id,
                self.service.name,
                type(error).__name__,
                extra={
                    "job_id": str(job.id),
                    "engine": self.service.name,
                    "status": "texture_failed",
                    "error_code": type(error).__name__,
                },
            )
            raise
