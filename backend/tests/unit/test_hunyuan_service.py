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

    assert result.artifact_relative_path == "hunyuan/model.glb"
    assert result.artifact_path.read_bytes() == b"glb"
    assert result.metadata["result_type"] in {"list", "tuple", "dict"}


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
