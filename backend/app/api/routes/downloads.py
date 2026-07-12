from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.dependencies import Container, get_container
from app.core.exceptions import ArtifactNotFoundError
from app.domain.jobs import JobStatus

router = APIRouter(tags=["downloads"])


@router.get("/download/{job_id}/textured")
def download_textured(
    job_id: UUID, container: Container = Depends(get_container)
) -> FileResponse:
    job = container.jobs.get(job_id)
    relative_path = job.texture_artifact_relative_path if job is not None else None
    if job is None or not relative_path:
        raise HTTPException(status_code=404, detail="Modelo texturizado não encontrado")
    try:
        artifact = container.storage.artifact_for_job(job_id, relative_path)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path=artifact, filename="model_textured.glb", media_type="model/gltf-binary"
    )


@router.get("/download/{job_id}")
def download(
    job_id: UUID, container: Container = Depends(get_container)
) -> FileResponse:
    job = container.jobs.get(job_id)
    try:
        if job is not None and job.status == JobStatus.COMPLETED:
            if not job.artifact_relative_path:
                raise ArtifactNotFoundError("Job sem artefato")
            artifact = container.storage.artifact_for_job(
                job_id, job.artifact_relative_path
            )
        else:
            # Compatibility with TripoSR artifacts generated before the job store.
            artifact = container.storage.triposr_artifact(job_id)
            if not artifact.is_file():
                raise ArtifactNotFoundError("Arquivo não encontrado")
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        path=artifact,
        filename="model.glb" if artifact.suffix.lower() == ".glb" else artifact.name,
        media_type=(
            "model/gltf-binary"
            if artifact.suffix.lower() == ".glb"
            else "application/octet-stream"
        ),
    )
