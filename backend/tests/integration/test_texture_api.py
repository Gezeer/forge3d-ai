import time
from pathlib import Path
from uuid import uuid4

from app.domain.jobs import Job, JobStatus
from app.texture.contracts import TextureResult
from app.texture.executor import TextureExecutor
from test_api import _client


class FakeTextureService:
    name = "hunyuan"

    def __init__(self, fail=False):
        self.fail = fail

    def available(self):
        return True

    def texture(self, context, mesh, image, request):
        if self.fail:
            raise RuntimeError("safe failure")
        output = context.job_dir / "model_textured.glb"
        output.write_bytes(b"pbr")
        return TextureResult(
            context.job_id,
            "textured",
            mesh,
            output,
            "model_textured.glb",
            "glb",
            {"resolution": request.resolution, "maps": ["albedo", "normal"]},
        )


def completed_job(tmp_path: Path, container):
    job_id = uuid4()
    job_dir = container.settings.output_dir / str(job_id)
    job_dir.mkdir(parents=True)
    (job_dir / "model.glb").write_bytes(b"white")
    (job_dir / "image.png").write_bytes(b"png")
    job = (
        Job.queued(job_id, "hunyuan")
        .transition(JobStatus.PROCESSING)
        .transition(JobStatus.COMPLETED, artifact_relative_path="model.glb")
    )
    container.jobs.save(job)
    return job


def test_texture_missing_and_shape_not_completed(tmp_path: Path):
    client, container = _client(tmp_path)
    queued = Job.queued(uuid4(), "hunyuan")
    container.jobs.save(queued)
    with client:
        assert (
            client.post(
                f"/jobs/{uuid4()}/texture", data={"engine": "hunyuan"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/jobs/{queued.id}/texture", data={"engine": "hunyuan"}
            ).status_code
            == 409
        )


def test_texture_is_queued_completed_and_downloadable(tmp_path: Path):
    client, container = _client(tmp_path)
    container.job_queue.texture_executor = TextureExecutor(
        container.jobs, FakeTextureService()
    )
    job = completed_job(tmp_path, container)
    with client:
        response = client.post(
            f"/jobs/{job.id}/texture",
            data={"engine": "hunyuan", "resolution": 2048, "quality": "standard"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "texture_queued"
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = client.get(f"/jobs/{job.id}").json()
            if status["texture_status"] == "textured":
                break
        assert status["status"] == "completed"
        assert status["texture_status"] == "textured"
        assert status["output_textured_glb"].endswith(
            f"outputs/{job.id}/model_textured.glb"
        )
        assert client.get(f"/download/{job.id}").content == b"white"
        assert client.get(f"/download/{job.id}/textured").content == b"pbr"


def test_api_v1_texture_preserves_professional_and_legacy_routes(tmp_path: Path):
    client, container = _client(tmp_path)
    container.job_queue.texture_executor = TextureExecutor(
        container.jobs, FakeTextureService()
    )
    job = completed_job(tmp_path, container)
    with client:
        response = client.post(
            "/api/v1/texture",
            data={"job_id": str(job.id), "quality": "standard"},
        )
        assert response.status_code == 202
        assert response.json()["status_url"] == f"/jobs/{job.id}"
        assert "/api/v1/texture" in client.get("/openapi.json").json()["paths"]
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = client.get(f"/jobs/{job.id}").json()
            if status["texture_status"] == "textured":
                break
        assert client.get(f"/download/{job.id}/textured").content == b"pbr"
        assert client.get(f"/jobs/{job.id}/texture").status_code == 200


def test_texture_failure_keeps_original(tmp_path: Path):
    client, container = _client(tmp_path)
    container.job_queue.texture_executor = TextureExecutor(
        container.jobs, FakeTextureService(True)
    )
    job = completed_job(tmp_path, container)
    with client:
        assert (
            client.post(
                f"/jobs/{job.id}/texture", data={"engine": "hunyuan"}
            ).status_code
            == 202
        )
    stored = container.jobs.get(job.id)
    assert stored.status == JobStatus.COMPLETED
    assert stored.texture_status.value == "texture_failed"
    assert (container.settings.output_dir / str(job.id) / "model.glb").exists()
