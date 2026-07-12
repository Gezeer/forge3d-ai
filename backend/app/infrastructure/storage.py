from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO, Optional
from uuid import UUID

from app.core.exceptions import ArtifactNotFoundError, InvalidUploadError


class LocalStorage:
    def __init__(self, upload_dir: Path, output_dir: Path) -> None:
        self.upload_dir = upload_dir
        self.output_dir = output_dir

    def initialize(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def safe_filename(filename: Optional[str]) -> str:
        if not filename:
            return "upload"
        normalized = filename.replace("\\", "/")
        candidate = Path(normalized).name
        if candidate in {"", ".", ".."}:
            raise InvalidUploadError("Nome de arquivo inválido")
        return candidate

    def create_job_dir(self, job_id: UUID) -> Path:
        job_dir = self.output_dir / str(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        return job_dir

    def save_upload(
        self, job_dir: Path, filename: Optional[str], source: BinaryIO
    ) -> Path:
        safe_name = self.safe_filename(filename)
        destination = job_dir / safe_name
        resolved_job = job_dir.resolve()
        if resolved_job not in destination.resolve().parents:
            raise InvalidUploadError("Caminho de upload inválido")
        with destination.open("wb") as target:
            shutil.copyfileobj(source, target)
        return destination

    def copy_artifact(self, source: Path, job_dir: Path, filename: str) -> Path:
        if not source.is_file():
            raise ArtifactNotFoundError("Artefato 3D não encontrado")
        destination = job_dir / self.safe_filename(filename)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        return destination

    def triposr_artifact(self, job_id: UUID) -> Path:
        return self.output_dir / str(job_id) / "0" / "mesh.glb"

    def artifact_for_job(self, job_id: UUID, relative_path: str) -> Path:
        job_dir = (self.output_dir / str(job_id)).resolve()
        artifact = (job_dir / relative_path).resolve()
        if job_dir not in artifact.parents:
            raise ArtifactNotFoundError("Caminho de artefato inválido")
        if not artifact.is_file():
            raise ArtifactNotFoundError("Arquivo não encontrado")
        return artifact
