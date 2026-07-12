from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, GenerationError
from app.infrastructure.subprocess_runner import ProcessResult
from app.services.triposr import TripoSRService


class FakeRunner:
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        self.command = None
        self.timeout = None

    def run(self, command, timeout: float) -> ProcessResult:
        self.command = list(command)
        self.timeout = timeout
        return self.result


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        output_dir=tmp_path,
        triposr_run=Path("/models/TripoSR/run.py"),
        triposr_python=Path("/venvs/triposr/bin/python"),
        generation_timeout_seconds=42,
    )


def test_triposr_preserves_existing_command_and_artifact_contract(
    tmp_path: Path,
) -> None:
    job_id = uuid4()
    job_dir = tmp_path / str(job_id)
    input_image = job_dir / "input.png"
    artifact = job_dir / "0" / "mesh.glb"
    artifact.parent.mkdir(parents=True)
    input_image.write_bytes(b"png")
    artifact.write_bytes(b"glb")
    runner = FakeRunner(ProcessResult(returncode=0))
    service = TripoSRService(_settings(tmp_path), runner)

    result = service.generate(job_id, input_image, job_dir)

    assert runner.command == [
        "/venvs/triposr/bin/python",
        "/models/TripoSR/run.py",
        str(input_image),
        "--device",
        "cuda:0",
        "--model-save-format",
        "glb",
        "--output-dir",
        str(job_dir),
    ]
    assert runner.timeout == 42
    assert result.artifact_path == artifact
    assert result.artifact_relative_path == "0/mesh.glb"


def test_triposr_reports_process_failure(tmp_path: Path) -> None:
    runner = FakeRunner(ProcessResult(returncode=1, stderr="private details"))
    service = TripoSRService(_settings(tmp_path), runner)
    job_dir = tmp_path / str(uuid4())

    with pytest.raises(GenerationError) as error:
        service.generate(uuid4(), job_dir / "input.png", job_dir)

    assert error.value.details == "private details"


def test_triposr_requires_zero_mesh_glb(tmp_path: Path) -> None:
    runner = FakeRunner(ProcessResult(returncode=0))
    service = TripoSRService(_settings(tmp_path), runner)
    job_dir = tmp_path / str(uuid4())
    job_dir.mkdir()

    with pytest.raises(ArtifactNotFoundError, match="mesh.glb"):
        service.generate(uuid4(), job_dir / "input.png", job_dir)
