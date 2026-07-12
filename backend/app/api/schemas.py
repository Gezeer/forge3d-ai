from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel

from app.domain.jobs import Job, JobStatus, TextureStatus


class GenerationResponse(BaseModel):
    status: str
    job_id: UUID
    engine: str
    download_url: str
    glb_exists: bool


class QueuedGenerationResponse(BaseModel):
    job_id: UUID
    engine: str
    status: JobStatus
    status_url: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class JobResponse(BaseModel):
    job_id: UUID
    engine: str
    status: JobStatus
    download_url: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    texture_status: Optional[TextureStatus] = None
    texture_download_url: Optional[str] = None
    texture_error: Optional[str] = None
    texture_metadata: Optional[Dict[str, Any]] = None
    output_textured_glb: Optional[str] = None

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        return cls(
            job_id=job.id,
            engine=job.engine,
            status=job.status,
            download_url=(
                f"/download/{job.id}" if job.status == JobStatus.COMPLETED else None
            ),
            error=job.error,
            metadata=job.metadata,
            texture_status=job.texture_status,
            texture_download_url=(
                f"/download/{job.id}/textured"
                if job.texture_status == TextureStatus.COMPLETED
                else None
            ),
            texture_error=job.texture_error,
            texture_metadata=job.texture_metadata,
            output_textured_glb=job.output_textured_glb,
        )


class TextureJobResponse(BaseModel):
    job_id: UUID
    engine: str
    status: TextureStatus
    status_url: str
    original_download_url: str
    textured_download_url: Optional[str] = None


class HealthResponse(BaseModel):
    api: str
    triposr_run_exists: bool
    hunyuan_configured: bool
    upload_dir: str
    output_dir: str
    engines: Dict[str, Dict[str, Any]]
    status: str
    queue: Dict[str, Any]
    job_repository: Dict[str, Any]
    storage: Dict[str, Any]
    version: str
