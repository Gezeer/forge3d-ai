from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.dependencies import Container, get_container
from app.api.schemas import (
    ErrorResponse,
    GenerationResponse,
    JobResponse,
    QueuedGenerationResponse,
)
from app.core.exceptions import (
    EngineRegistryError,
    GenerationError,
    GenerationTimeoutError,
    InvalidUploadError,
    JobQueueFullError,
    ServiceUnavailableError,
)
from app.domain.jobs import Job, JobStatus
from app.engines.contracts import Engine, JobContext
from app.queue.contracts import QueuedJob

router = APIRouter(tags=["generation"])


def _http_error(error: Exception, container: Container) -> HTTPException:
    if isinstance(error, InvalidUploadError):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, GenerationTimeoutError):
        return HTTPException(
            status_code=504,
            detail=str(error),
            headers={"X-Error-Code": "generation_timeout"},
        )
    if isinstance(error, ServiceUnavailableError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(error, EngineRegistryError):
        return HTTPException(
            status_code=503,
            detail=str(error),
            headers={"X-Error-Code": "engine_unavailable"},
        )
    if isinstance(error, JobQueueFullError):
        return HTTPException(
            status_code=503,
            detail=str(error),
            headers={"X-Error-Code": "queue_full"},
        )
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
    try:
        container.validator.validate_metadata(file.content_type)
        container.validator.validate_size(file.file)
        job_dir = container.storage.create_job_dir(job_id)
        input_image = container.storage.save_upload(job_dir, file.filename, file.file)
        task = QueuedJob(
            job=job,
            context=JobContext(job_id, job_dir),
            image_path=input_image,
        )
        result = container.executor.execute(task)
    except Exception as error:
        current = container.jobs.get(job_id)
        if current is not None and current.status == JobStatus.QUEUED:
            container.jobs.save(current.transition(JobStatus.FAILED, error=str(error)))
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


def _select_engine(requested: str, container: Container) -> Engine:
    normalized = requested.strip().lower()
    if normalized == "auto":
        return container.auto_policy.select()
    return container.engines.get(normalized)


@router.post(
    "/jobs/generate",
    response_model=QueuedGenerationResponse,
    status_code=202,
    summary="Enfileirar geração 3D",
    description=(
        "Aceita uma imagem e responde imediatamente. Use status_url para "
        "acompanhar queued, processing, completed ou failed."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Upload inválido"},
        422: {"model": ErrorResponse, "description": "Formulário inválido"},
        503: {"model": ErrorResponse, "description": "Fila ou engine indisponível"},
    },
)
@router.post(
    "/api/v1/generate",
    response_model=QueuedGenerationResponse,
    status_code=202,
    summary="Enfileirar geração 3D (API v1)",
    responses={
        400: {"model": ErrorResponse, "description": "Upload inválido"},
        422: {"model": ErrorResponse, "description": "Formulário inválido"},
        503: {"model": ErrorResponse, "description": "Fila ou engine indisponível"},
    },
)
def enqueue_generation(
    file: UploadFile = File(...),
    engine: str = Form(""),
    container: Container = Depends(get_container),
) -> QueuedGenerationResponse:
    requested = engine or container.settings.default_engine
    try:
        selected = _select_engine(requested, container)
        container.validator.validate_metadata(file.content_type)
        container.validator.validate_size(file.file)
        job_id = uuid4()
        job_dir = container.storage.create_job_dir(job_id)
        image_path = container.storage.save_upload(job_dir, file.filename, file.file)
        job = Job.queued(job_id, selected.name)
        container.job_queue.enqueue(
            QueuedJob(
                job=job,
                context=JobContext(job_id, job_dir),
                image_path=image_path,
            )
        )
    except Exception as error:
        raise _http_error(error, container) from error
    finally:
        file.file.close()

    return QueuedGenerationResponse(
        job_id=job_id,
        engine=selected.name,
        status=JobStatus.QUEUED,
        status_url=f"/jobs/{job_id}",
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
        engine = _select_engine("auto", container)
    except EngineRegistryError as error:
        raise _http_error(error, container) from error
    return _generate(file, engine, container)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, container: Container = Depends(get_container)) -> JobResponse:
    job = container.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    textured_exists = False
    if job.texture_artifact_relative_path:
        try:
            textured_exists = container.storage.artifact_for_job(
                job.id, job.texture_artifact_relative_path
            ).is_file()
        except GenerationError:
            textured_exists = False
    return JobResponse.from_job(job, textured_exists=textured_exists)
