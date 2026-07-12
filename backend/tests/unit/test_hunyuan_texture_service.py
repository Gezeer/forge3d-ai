from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.core.exceptions import (
    GenerationTimeoutError,
    ServiceUnavailableError,
)
from app.engines.contracts import JobContext
from app.infrastructure.subprocess_runner import ProcessResult
from app.texture.contracts import TextureRequest
from app.texture.hunyuan import HunyuanTextureService


class TextureRunner:
    def __init__(self, returncode=0, error=None):
        self.returncode = returncode
        self.error = error

    def run(self, command, timeout):
        if self.error:
            raise self.error
        if self.returncode == 0:
            Path(command[-1]).write_bytes(b"textured-glb")
        return ProcessResult(self.returncode, stderr="private")


def settings(tmp_path: Path) -> Settings:
    root = tmp_path / "Hunyuan"
    root.mkdir()
    return Settings(
        texture_root=root,
        texture_command_json='["paint","{mesh}","{image}","{resolution}","{quality}","{output}"]',
        texture_timeout_seconds=4,
    )


def test_texture_service_creates_textured_glb_and_metadata(tmp_path: Path):
    config = settings(tmp_path)
    service = HunyuanTextureService(config, TextureRunner())
    job_id = uuid4()
    job_dir = tmp_path / str(job_id)
    job_dir.mkdir()
    mesh = job_dir / "model.glb"
    mesh.write_bytes(b"white")
    image = job_dir / "image.png"
    image.write_bytes(b"png")
    result = service.texture(
        JobContext(job_id, job_dir), mesh, image, TextureRequest(2048, "high")
    )
    assert result.artifact_path == job_dir / "model_textured.glb"
    assert result.artifact_path.read_bytes() == b"textured-glb"
    assert mesh.read_bytes() == b"white"
    assert result.metadata["resolution"] == 2048
    assert result.metadata["size_bytes"] > 0


def test_texture_service_reports_unavailable_dependency(tmp_path: Path):
    config = Settings(texture_root=tmp_path, texture_command_json="")
    with pytest.raises(ServiceUnavailableError):
        HunyuanTextureService(config, TextureRunner()).texture(
            JobContext(uuid4(), tmp_path),
            tmp_path / "model.glb",
            tmp_path / "image.png",
            TextureRequest(1024, "fast"),
        )


def test_texture_service_preserves_original_on_failure(tmp_path: Path):
    config = settings(tmp_path)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    mesh = job_dir / "model.glb"
    mesh.write_bytes(b"white")
    image = job_dir / "image.png"
    image.write_bytes(b"png")
    with pytest.raises(ServiceUnavailableError):
        HunyuanTextureService(config, TextureRunner(1)).texture(
            JobContext(uuid4(), job_dir), mesh, image, TextureRequest(1024, "standard")
        )
    assert mesh.read_bytes() == b"white"
    assert not (job_dir / "model_textured.glb").exists()


def test_texture_timeout_is_propagated(tmp_path: Path):
    config = settings(tmp_path)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    mesh = job_dir / "model.glb"
    mesh.write_bytes(b"white")
    image = job_dir / "image.png"
    image.write_bytes(b"png")
    with pytest.raises(GenerationTimeoutError):
        HunyuanTextureService(
            config, TextureRunner(error=GenerationTimeoutError("timeout"))
        ).texture(
            JobContext(uuid4(), job_dir), mesh, image, TextureRequest(1024, "standard")
        )
