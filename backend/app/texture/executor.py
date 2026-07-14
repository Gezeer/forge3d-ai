from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core.exceptions import TexturePipelineError
from app.domain.jobs import Job, JobRepository, TextureStatus
from app.engines.contracts import JobContext
from app.gpu.lock import GPULock
from app.gpu.memory import query_gpu_memory
from app.hunyuan.process_manager import HunyuanProcessManager
from app.texture.contracts import TextureRequest, TextureService

logger = logging.getLogger("forge3d.texture")


class TextureCycleError(RuntimeError):
    def __init__(self, primary: Exception, restart: Optional[Exception]) -> None:
        super().__init__(str(primary))
        self.primary = primary
        self.restart = restart


@dataclass(frozen=True)
class TextureQueuedJob:
    job: Job
    context: JobContext
    mesh_path: Path
    reference_image: Path
    request: TextureRequest


class TextureExecutor:
    def __init__(
        self,
        jobs: JobRepository,
        service: TextureService,
        *,
        process_manager: Optional[HunyuanProcessManager] = None,
        gpu_lock: Optional[GPULock] = None,
        memory_probe: Callable[[], Optional[dict[str, int]]] = query_gpu_memory,
    ) -> None:
        self.jobs = jobs
        self.service = service
        self.process_manager = process_manager
        self.gpu_lock = gpu_lock
        self.memory_probe = memory_probe

    def _execute_service(self, task: TextureQueuedJob):
        if self.process_manager is None or self.gpu_lock is None:
            return self.service.texture(
                task.context, task.mesh_path, task.reference_image, task.request
            )
        primary_error: Optional[Exception] = None
        restart_error: Optional[Exception] = None
        result = None
        with self.gpu_lock:
            try:
                self.process_manager.stop_shape_server()
                memory = self.memory_probe()
                if memory is not None:
                    logger.info(
                        "gpu_memory_before_paint total_mib=%s used_mib=%s free_mib=%s",
                        memory["total_mib"],
                        memory["used_mib"],
                        memory["free_mib"],
                        extra=memory,
                    )
                result = self.service.texture(
                    task.context,
                    task.mesh_path,
                    task.reference_image,
                    task.request,
                )
            except Exception as error:
                primary_error = error
            finally:
                try:
                    self.process_manager.ensure_shape_running()
                except Exception as error:
                    restart_error = error
                    logger.error(
                        "restart_failed error_code=%s",
                        type(error).__name__,
                        extra={"error_code": type(error).__name__},
                    )
        if primary_error is not None:
            raise TextureCycleError(primary_error, restart_error)
        if restart_error is not None:
            restart_failure = TexturePipelineError(
                "restart_shape", "Textura concluída, mas Hunyuan Shape não reiniciou"
            )
            raise TextureCycleError(restart_failure, restart_error)
        return result

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
            result = self._execute_service(task)
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
            effective_error = (
                error.primary if isinstance(error, TextureCycleError) else error
            )
            restart_error = (
                error.restart if isinstance(error, TextureCycleError) else None
            )
            error_payload = (
                effective_error.to_dict()
                if isinstance(effective_error, TexturePipelineError)
                else {
                    "status": "error",
                    "step": "texture",
                    "message": "Falha na texturização",
                }
            )
            if restart_error is not None:
                error_payload["restart_error"] = "Falha ao reiniciar Hunyuan Shape"
                error_payload["restart_error_code"] = type(restart_error).__name__
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
                type(effective_error).__name__,
                extra={
                    "job_id": str(job.id),
                    "engine": self.service.name,
                    "status": "failed",
                    "duration_seconds": round(duration, 3),
                    "error_code": type(effective_error).__name__,
                    "step": error_payload["step"],
                },
            )
            if isinstance(error, TextureCycleError):
                raise effective_error from error
            raise
