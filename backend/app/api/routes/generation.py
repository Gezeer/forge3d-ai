from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.dependencies import Container, get_container
from app.api.schemas import GenerationResponse, JobResponse
from app.core.exceptions import (
    Forge3DError,
    EngineRegistryError,
    GenerationError,
    GenerationTimeoutError,
    InvalidUploadError,
    ServiceUnavailableError,
)
from app.domain.jobs import Job, JobStatus
from app.engines.contracts import Engine, JobContext


router = APIRouter(tags=["generation"])


def _http_error(error: Exception, container: Container) -> HTTPException:
    if isinstance(error, InvalidUploadError):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, GenerationTimeoutError):
        return HTTPException(status_code=504, detail=str(error))
    if isinstance(error, ServiceUnavailableError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, EngineRegistryError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, GenerationError):
        detail = str(error)
        if container.settings.expose_process_details and error.details:
            detail = f"{detail}: {error.details}"
        return HTTPException(status_code=500, detail=detail)
    return HTTPException(status_code=500, detail="Falha interna na geração")


def _generate(
    file: UploadFile, engine: Engine, container: Container
) -> GenerationResponse:
    job_id = uuid4()
    job = Job.queued(job_id, engine.name)
    container.jobs.save(job)
    job_dir = None
    try:
        container.validator.validate_metadata(file.content_type)
        container.validator.validate_size(file.file)
        job_dir = container.storage.create_job_dir(job_id)
        input_image = container.storage.save_upload(job_dir, file.filename, file.file)
        job = container.jobs.save(job.transition(JobStatus.PROCESSING))
        result = engine.generate(JobContext(job_id, job_dir), input_image)
        job = container.jobs.save(
            job.transition(
                JobStatus.COMPLETED,
                artifact_relative_path=result.artifact_relative_path,
                metadata=result.metadata,
            )
        )
    except Exception as error:
        if job.status in {JobStatus.QUEUED, JobStatus.PROCESSING}:
            container.jobs.save(job.transition(JobStatus.FAILED, error=str(error)))
        raise _http_error(error, container) from error
    finally:
        file.file.close()

    return GenerationResponse(
        status="success",
        job_id=job_id,
        engine=engine.name,
        download_url=f"/download/{job_id}",
        glb_exists=result.artifact_path.suffix.lower() == ".glb",
    )


@router.post("/generate/image", response_model=GenerationResponse)
def generate_image(
    file: UploadFile = File(...),
    container: Container = Depends(get_container),
) -> GenerationResponse:
    """Temporary compatibility alias for TripoSR."""
    return _generate(file, container.engines.get("triposr"), container)


@router.post("/generate/triposr", response_model=GenerationResponse)
def generate_triposr(
    file: UploadFile = File(...),
    container: Container = Depends(get_container),
) -> GenerationResponse:
    return _generate(file, container.engines.get("triposr"), container)


@router.post("/generate/hunyuan", response_model=GenerationResponse)
def generate_hunyuan(
    file: UploadFile = File(...),
    container: Container = Depends(get_container),
) -> GenerationResponse:
    return _generate(file, container.engines.get("hunyuan"), container)


@router.post("/generate/auto", response_model=GenerationResponse)
def generate_auto(
    file: UploadFile = File(...),
    container: Container = Depends(get_container),
) -> GenerationResponse:
    try:
        engine = container.auto_policy.select()
    except EngineRegistryError as error:
        raise _http_error(error, container) from error
    return _generate(file, engine, container)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: UUID, container: Container = Depends(get_container)
) -> JobResponse:
    job = container.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return JobResponse.from_job(job)
