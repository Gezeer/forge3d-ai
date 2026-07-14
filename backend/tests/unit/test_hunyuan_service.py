from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError
from app.engines.contracts import JobContext
from app.infrastructure.hunyuan_client import HunyuanResult
from app.infrastructure.storage import LocalStorage
from app.services.hunyuan import HunyuanService


class FakeGateway:
    def __init__(self, result) -> None:
        self.result = result
        self.call = None

    def generate(self, image_path, timeout):
        self.call = (image_path, timeout)
        return HunyuanResult(
            self.result,
            {
                "steps": 30,
                "guidance_scale": 5.0,
                "seed": 1234,
                "octree_resolution": 256,
            },
        )

    def available(self, timeout) -> bool:
        return True

    def diagnostics(self):
        return {"openapi": "available", "endpoint": "/run/shape_generation"}


def _service(tmp_path: Path, result) -> HunyuanService:
    settings = Settings(
        upload_dir=tmp_path / "uploads",
        output_dir=tmp_path / "outputs",
        generation_timeout_seconds=12,
    )
    storage = LocalStorage(settings.upload_dir, settings.output_dir)
    return HunyuanService(
        settings,
        storage,
        FakeGateway(result),
    )


@pytest.mark.parametrize(
    "wrapped",
    [
        lambda path: [None, str(path)],
        lambda path: ("preview", path),
        lambda path: {"model": {"path": str(path)}},
    ],
)
def test_hunyuan_normalizes_and_copies_supported_results(
    tmp_path: Path, wrapped
) -> None:
    source = tmp_path / "remote-result.glb"
    source.write_bytes(b"glb")
    service = _service(tmp_path, wrapped(source))
    job_id = uuid4()
    job_dir = tmp_path / "outputs" / str(job_id)
    job_dir.mkdir(parents=True)

    result = service.generate(JobContext(job_id, job_dir), tmp_path / "image.png")

    assert result.artifact_relative_path == "model.glb"
    assert result.artifact_path.read_bytes() == b"glb"
    assert result.metadata["result_type"] in {"list", "tuple", "dict"}
    assert result.metadata["extension"] == ".glb"
    assert result.metadata["size_bytes"] == 3
    assert result.metadata["origin"] == "local"


def test_hunyuan_health_uses_openapi_client(tmp_path: Path) -> None:
    service = _service(tmp_path, [])

    health = service.health()

    assert health.available is True
    assert health.details["api_name"] == "/run/shape_generation"
    assert health.details["openapi"] == "available"


def test_hunyuan_rejects_unexpected_return(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        result={"status": "done", "preview": "not-an-artifact"},
    )
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    with pytest.raises(ArtifactNotFoundError, match="nenhum artefato"):
        service.generate(JobContext(uuid4(), job_dir), tmp_path / "image.png")


def test_hunyuan_materializes_filedata_remote_url(tmp_path: Path) -> None:
    downloaded = []

    def downloader(url, destination):
        downloaded.append(url)
        destination.write_bytes(b"remote-glb")

    settings = Settings(upload_dir=tmp_path / "uploads", output_dir=tmp_path)
    storage = LocalStorage(settings.upload_dir, settings.output_dir)
    service = HunyuanService(
        settings,
        storage,
        FakeGateway(
            {"path": None, "url": "https://signed.example/model.glb?token=SECRET"}
        ),
        downloader=downloader,
    )
    job_id = uuid4()
    job_dir = tmp_path / str(job_id)
    job_dir.mkdir()

    result = service.generate(JobContext(job_id, job_dir), tmp_path / "image.png")

    assert result.artifact_path == job_dir / "model.glb"
    assert result.artifact_path.read_bytes() == b"remote-glb"
    assert result.metadata["origin"] == "remote"
    assert "url" not in result.metadata
    assert downloaded == ["https://signed.example/model.glb?token=SECRET"]


def test_hunyuan_normalizes_real_shape_generation_tuple_and_mesh_stats(
    tmp_path: Path,
) -> None:
    source = tmp_path / "white_mesh.glb"
    source.write_bytes(b"valid-glb")
    real_result = (
        {"value": str(source), "**type**": "update"},
        "<html>preview</html>",
        {
            "number_of_faces": 1200,
            "number_of_vertices": 700,
            "total_time": 9.5,
        },
        4321,
    )
    service = _service(tmp_path, real_result)
    job_id = uuid4()
    job_dir = tmp_path / "outputs" / str(job_id)
    job_dir.mkdir(parents=True)

    result = service.generate(JobContext(job_id, job_dir), tmp_path / "image.png")

    assert result.artifact_path == job_dir / "model.glb"
    assert result.artifact_path.read_bytes() == b"valid-glb"
    assert "white_mesh" not in result.artifact_relative_path
    assert str(source) not in str(result.metadata)
    assert result.metadata["number_of_faces"] == 1200
    assert result.metadata["number_of_vertices"] == 700
    assert result.metadata["total_time"] == 9.5
    assert result.metadata["steps"] == 30
    assert result.metadata["guidance_scale"] == 5.0
    assert result.metadata["seed"] == 4321
    assert result.metadata["octree_resolution"] == 256


def test_hunyuan_update_value_must_exist(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        ({"value": "/tmp/missing/white_mesh.glb", "**type**": "update"},),
    )
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    with pytest.raises(ArtifactNotFoundError):
        service.generate(JobContext(uuid4(), job_dir), tmp_path / "image.png")


def test_hunyuan_update_value_rejects_unsupported_extension(tmp_path: Path) -> None:
    source = tmp_path / "mesh.gltf"
    source.write_text("unsupported")
    service = _service(
        tmp_path,
        ({"value": str(source), "**type**": "update"},),
    )
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    with pytest.raises(ArtifactNotFoundError):
        service.generate(JobContext(uuid4(), job_dir), tmp_path / "image.png")
