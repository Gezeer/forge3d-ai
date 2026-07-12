from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.core.exceptions import ArtifactNotFoundError, ServiceUnavailableError
from app.engines.contracts import JobContext
from app.infrastructure.hunyuan_gateway import HunyuanSignature
from app.infrastructure.storage import LocalStorage
from app.services.hunyuan import HunyuanService


class FakeGateway:
    def __init__(self, result) -> None:
        self.result = result
        self.call = None

    def predict(self, image_path, signature, api_name, timeout):
        self.call = (image_path, signature, api_name, timeout)
        return self.result

    def available(self) -> bool:
        return True


def _service(tmp_path: Path, result, signature=None) -> HunyuanService:
    settings = Settings(
        upload_dir=tmp_path / "uploads",
        output_dir=tmp_path / "outputs",
        generation_timeout_seconds=12,
        hunyuan_signature_json="",
    )
    storage = LocalStorage(settings.upload_dir, settings.output_dir)
    return HunyuanService(
        settings,
        storage,
        FakeGateway(result),
        signature=signature,
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
    signature = HunyuanSignature(args=[{"$image": True}])
    service = _service(tmp_path, wrapped(source), signature)
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


def test_hunyuan_refuses_to_guess_signature(tmp_path: Path) -> None:
    service = _service(tmp_path, result=[])

    with pytest.raises(ServiceUnavailableError, match="Assinatura"):
        service.generate(JobContext(uuid4(), tmp_path / "job"), tmp_path / "image.png")


def test_hunyuan_rejects_unexpected_return(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        result={"status": "done", "preview": "not-an-artifact"},
        signature=HunyuanSignature(args=[]),
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
        signature=HunyuanSignature(args=[]),
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
    signature = HunyuanSignature(
        args=[
            {"$image": "simple"},
            None,
            None,
            None,
            None,
            30,
            5.0,
            1234,
            256,
            True,
            8000,
            False,
        ]
    )
    service = _service(tmp_path, real_result, signature)
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
        HunyuanSignature(args=[]),
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
        HunyuanSignature(args=[]),
    )
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    with pytest.raises(ArtifactNotFoundError):
        service.generate(JobContext(uuid4(), job_dir), tmp_path / "image.png")
