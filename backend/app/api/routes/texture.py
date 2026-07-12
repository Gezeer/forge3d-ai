from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.dependencies import Container, get_container
from app.api.schemas import TextureJobResponse
from app.domain.jobs import JobStatus, TextureStatus
from app.engines.contracts import JobContext
from app.texture.contracts import TextureRequest
from app.texture.executor import TextureQueuedJob

router = APIRouter(tags=["texture"])


def _reference_image(job_dir: Path) -> Path:
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidates = list(job_dir.glob(f"*{suffix}"))
        if candidates:
            return candidates[0]
    raise HTTPException(status_code=404, detail="Imagem de referência não encontrada")


@router.post(
    "/jobs/{job_id}/texture",
    response_model=TextureJobResponse,
    status_code=202,
    summary="Enfileirar texturização PBR",
)
def create_texture_job(
    job_id: UUID,
    file: UploadFile = File(None),
    engine: str = Form("hunyuan"),
    resolution: int = Form(2048),
    quality: str = Form("standard"),
    container: Container = Depends(get_container),
) -> TextureJobResponse:
    job = container.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if job.status != JobStatus.COMPLETED or not job.artifact_relative_path:
        raise HTTPException(status_code=409, detail="Shape ainda não concluído")
    if engine != "hunyuan" or quality not in {"fast", "standard", "high"}:
        raise HTTPException(status_code=422, detail="Configuração de textura inválida")
    if resolution < 512 or resolution > 4096:
        raise HTTPException(status_code=422, detail="Resolução de textura inválida")
    job_dir = container.settings.output_dir / str(job_id)
    mesh = container.storage.artifact_for_job(job_id, job.artifact_relative_path)
    try:
        if file is not None:
            container.validator.validate_metadata(file.content_type)
            container.validator.validate_size(file.file)
            reference = container.storage.save_upload(
                job_dir, f"texture_{file.filename}", file.file
            )
        else:
            reference = _reference_image(job_dir)
    finally:
        if file is not None:
            file.file.close()
    queued = job.transition_texture(TextureStatus.QUEUED)
    container.job_queue.enqueue_texture(
        TextureQueuedJob(
            queued,
            JobContext(job_id, job_dir),
            mesh,
            reference,
            TextureRequest(resolution, quality),
        )
    )
    return TextureJobResponse(
        job_id=job_id,
        engine=engine,
        status=TextureStatus.QUEUED,
        status_url=f"/jobs/{job_id}",
        original_download_url=f"/download/{job_id}",
    )


@router.get("/jobs/{job_id}/texture", response_model=TextureJobResponse)
def texture_status(
    job_id: UUID, container: Container = Depends(get_container)
) -> TextureJobResponse:
    job = container.jobs.get(job_id)
    if job is None or job.texture_status is None:
        raise HTTPException(status_code=404, detail="Estágio de textura não encontrado")
    return TextureJobResponse(
        job_id=job.id,
        engine="hunyuan",
        status=job.texture_status,
        status_url=f"/jobs/{job.id}",
        original_download_url=f"/download/{job.id}",
        textured_download_url=f"/download/{job.id}/textured"
        if job.texture_status == TextureStatus.COMPLETED
        else None,
    )
