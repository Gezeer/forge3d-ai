from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import Container
from app.core.config import Settings
from app.core.exceptions import GenerationError, GenerationTimeoutError
from app.domain.generation import GenerationResult
from app.domain.jobs import Job, JobStatus
from app.infrastructure.job_repository import MemoryJobRepository
from app.infrastructure.storage import LocalStorage
from app.main import create_app
from app.services.upload_validation import UploadValidator


class FakeGenerator:
    def __init__(self, engine: str = "triposr", error=None) -> None:
        self.engine = engine
        self.error = error
        self.input_image = None

    def generate(self, job_id, input_image, job_dir):
        self.input_image = input_image
        if self.error:
            raise self.error
        if self.engine == "triposr":
            artifact = job_dir / "0" / "mesh.glb"
            relative = "0/mesh.glb"
        else:
            artifact = job_dir / "hunyuan" / "model.glb"
            relative = "hunyuan/model.glb"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"glb")
        return GenerationResult(
            job_id=job_id,
            engine=self.engine,
            artifact_path=artifact,
            artifact_relative_path=relative,
        )


def _client(
    tmp_path: Path,
    *,
    triposr=None,
    hunyuan=None,
    environment: str = "test",
    max_bytes: int = 1024,
    auto_engine: str = "triposr",
):
    settings = Settings(
        upload_dir=tmp_path / "uploads",
        output_dir=tmp_path / "outputs",
        jobs_file=tmp_path / "outputs" / "jobs.json",
        environment=environment,
        upload_max_bytes=max_bytes,
        auto_engine=auto_engine,
    )
    storage = LocalStorage(settings.upload_dir, settings.output_dir)
    container = Container(
        settings=settings,
        storage=storage,
        jobs=MemoryJobRepository(),
        validator=UploadValidator(settings.allowed_image_types, max_bytes),
        triposr=triposr or FakeGenerator("triposr"),
        hunyuan=hunyuan or FakeGenerator("hunyuan"),
    )
    return TestClient(create_app(settings, container)), container


@pytest.mark.parametrize(
    "endpoint", ["/generate/image", "/generate/triposr", "/generate/auto"]
)
def test_triposr_routes_generate_track_and_download(
    tmp_path: Path, endpoint: str
) -> None:
    client, _ = _client(tmp_path)

    with client:
        response = client.post(
            endpoint,
            files={"file": ("chair.png", b"png", "image/png")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "success"
        assert body["engine"] == "triposr"
        assert body["glb_exists"] is True

        job = client.get(f"/jobs/{body['job_id']}")
        assert job.json()["status"] == "completed"
        download = client.get(body["download_url"])
        assert download.status_code == 200
        assert download.content == b"glb"
        assert download.headers["content-type"] == "model/gltf-binary"


def test_hunyuan_and_auto_can_use_injected_engine(tmp_path: Path) -> None:
    client, _ = _client(tmp_path, auto_engine="hunyuan")

    with client:
        for endpoint in ("/generate/hunyuan", "/generate/auto"):
            response = client.post(
                endpoint,
                files={"file": ("object.webp", b"webp", "image/webp")},
            )
            assert response.status_code == 200
            assert response.json()["engine"] == "hunyuan"


def test_upload_validation_and_path_sanitization(tmp_path: Path) -> None:
    generator = FakeGenerator()
    client, _ = _client(tmp_path, triposr=generator, max_bytes=4)

    with client:
        invalid_type = client.post(
            "/generate/image",
            files={"file": ("note.txt", b"x", "text/plain")},
        )
        too_large = client.post(
            "/generate/image",
            files={"file": ("image.png", b"12345", "image/png")},
        )
        safe = client.post(
            "/generate/image",
            files={"file": ("../../image.png", b"png", "image/png")},
        )

    assert invalid_type.status_code == 400
    assert too_large.status_code == 400
    assert safe.status_code == 200
    assert generator.input_image.name == "image.png"
    assert ".." not in generator.input_image.parts


def test_failed_job_and_timeout_are_recorded(tmp_path: Path) -> None:
    generator = FakeGenerator(
        error=GenerationTimeoutError("tempo limite", details="private")
    )
    client, container = _client(tmp_path, triposr=generator)

    with client:
        response = client.post(
            "/generate/image",
            files={"file": ("image.png", b"png", "image/png")},
        )

    assert response.status_code == 504
    failed = next(iter(container.jobs._jobs.values()))
    assert failed.status == JobStatus.FAILED
    assert failed.error == "tempo limite"


def test_production_response_does_not_expose_stderr(tmp_path: Path) -> None:
    generator = FakeGenerator(
        error=GenerationError("generation failed", details="SECRET STDERR")
    )
    client, _ = _client(tmp_path, triposr=generator, environment="production")

    with client:
        response = client.post(
            "/generate/image",
            files={"file": ("image.png", b"png", "image/png")},
        )

    assert response.status_code == 500
    assert "SECRET STDERR" not in response.text


def test_download_validates_uuid_and_blocks_artifact_traversal(tmp_path: Path) -> None:
    client, container = _client(tmp_path)
    job_id = uuid4()
    job = Job.queued(job_id, "triposr").transition(JobStatus.PROCESSING)
    job = job.transition(
        JobStatus.COMPLETED, artifact_relative_path="../../outside.glb"
    )
    container.jobs.save(job)

    with client:
        invalid_uuid = client.get("/download/not-a-uuid")
        traversal = client.get(f"/download/{job_id}")

    assert invalid_uuid.status_code == 422
    assert traversal.status_code == 404


def test_legacy_download_finds_existing_triposr_artifact(tmp_path: Path) -> None:
    client, container = _client(tmp_path)
    job_id = uuid4()
    artifact = container.storage.triposr_artifact(job_id)
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"legacy")

    with client:
        response = client.get(f"/download/{job_id}")

    assert response.status_code == 200
    assert response.content == b"legacy"


def test_health_does_not_connect_to_remote_services(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    with client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["api"] == "ok"
    assert response.json()["hunyuan_configured"] is False
