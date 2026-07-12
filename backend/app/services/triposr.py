from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, GenerationError
from app.domain.generation import GenerationResult
from app.engines.contracts import EngineHealth, JobContext
from app.infrastructure.subprocess_runner import ProcessRunner


class TripoSRService:
    """Runs the existing RunPod TripoSR CLI without loading it in the API process."""

    name = "triposr"

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

    def available(self) -> bool:
        return (
            self.settings.triposr_python.is_file()
            and self.settings.triposr_run.is_file()
        )

    def health(self) -> EngineHealth:
        return EngineHealth(
            name=self.name,
            available=self.available(),
            details={
                "run_exists": self.settings.triposr_run.is_file(),
                "python_exists": self.settings.triposr_python.is_file(),
                "device": self.settings.triposr_device,
            },
        )

    def generate(self, job_context: JobContext, input_image: Path) -> GenerationResult:
        job_id = job_context.job_id
        job_dir = job_context.job_dir
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
            engine=self.name,
            artifact_path=artifact,
            artifact_relative_path="0/mesh.glb",
            metadata={"return_code": process.returncode},
        )
