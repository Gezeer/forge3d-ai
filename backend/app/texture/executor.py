from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import TexturePipelineError
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
        started = time.monotonic()
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
            output_path = f"outputs/{job.id}/{result.artifact_relative_path}"
            completed = self.jobs.save(
                job.transition_texture(
                    TextureStatus.COMPLETED,
                    artifact_relative_path=result.artifact_relative_path,
                    output_textured_glb=output_path,
                    metadata=result.metadata,
                )
            )
            duration = time.monotonic() - started
            logger.info(
                "texture_state_changed job_id=%s engine=%s status=completed duration=%.3f size=%s",
                completed.id,
                self.service.name,
                duration,
                result.metadata.get("size_bytes", 0),
                extra={
                    "job_id": str(completed.id),
                    "engine": self.service.name,
                    "status": "completed",
                    "duration_seconds": round(duration, 3),
                    "size_bytes": result.metadata.get("size_bytes", 0),
                },
            )
            return result
        except Exception as error:
            duration = time.monotonic() - started
            error_payload = (
                error.to_dict()
                if isinstance(error, TexturePipelineError)
                else {
                    "status": "error",
                    "step": "texture",
                    "message": "Falha na texturização",
                }
            )
            self.jobs.save(
                job.transition_texture(
                    TextureStatus.FAILED,
                    error=error_payload["message"],
                    metadata=error_payload,
                )
            )
            logger.error(
                "texture_state_changed job_id=%s engine=%s status=failed duration=%.3f error_code=%s",
                job.id,
                self.service.name,
                duration,
                type(error).__name__,
                extra={
                    "job_id": str(job.id),
                    "engine": self.service.name,
                    "status": "failed",
                    "duration_seconds": round(duration, 3),
                    "error_code": type(error).__name__,
                    "step": error_payload["step"],
                },
            )
            raise
