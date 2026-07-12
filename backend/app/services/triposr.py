from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, GenerationError
from app.domain.generation import GenerationResult
from app.infrastructure.subprocess_runner import ProcessRunner


class TripoSRService:
    """Runs the existing RunPod TripoSR CLI without loading it in the API process."""

    engine = "triposr"

    def __init__(self, settings: Settings, runner: ProcessRunner) -> None:
        self.settings = settings
        self.runner = runner

    def command(self, input_image: Path, job_dir: Path) -> list[str]:
        return [
            str(self.settings.triposr_python),
            str(self.settings.triposr_run),
            str(input_image),
            "--device",
            self.settings.triposr_device,
            "--model-save-format",
            "glb",
            "--output-dir",
            str(job_dir),
        ]

    def generate(
        self, job_id: UUID, input_image: Path, job_dir: Path
    ) -> GenerationResult:
        process = self.runner.run(
            self.command(input_image, job_dir),
            timeout=self.settings.generation_timeout_seconds,
        )
        if process.returncode != 0:
            raise GenerationError(
                "TripoSR não conseguiu gerar o modelo",
                details=process.stderr,
            )

        artifact = job_dir / "0" / "mesh.glb"
        if not artifact.is_file():
            raise ArtifactNotFoundError(
                "mesh.glb não foi gerado",
                details=process.stderr,
            )

        return GenerationResult(
            job_id=job_id,
            engine=self.engine,
            artifact_path=artifact,
            artifact_relative_path="0/mesh.glb",
            metadata={"return_code": process.returncode},
        )
