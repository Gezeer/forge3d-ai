from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from app.core.exceptions import TexturePipelineError
from app.domain.jobs import Job, JobStatus, TextureStatus
from app.engines.contracts import JobContext
from app.infrastructure.job_repository import MemoryJobRepository
from app.texture.contracts import TextureRequest, TextureResult
from app.texture.executor import TextureExecutor, TextureQueuedJob


class Lock:
    def __init__(self):
        self.entered = 0
        self.exited = 0

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *args):
        self.exited += 1


class Manager:
    def __init__(self, restart_error=None):
        self.calls = []
        self.restart_error = restart_error

    def stop_shape_server(self):
        self.calls.append("stop")

    def ensure_shape_running(self):
        self.calls.append("restart")
        if self.restart_error:
            raise self.restart_error


class Service:
    name = "hunyuan"

    def __init__(self, jobs, job_id, error=None):
        self.jobs = jobs
        self.job_id = job_id
        self.error = error

    def texture(self, context, mesh, image, request):
        assert self.jobs.get(self.job_id).texture_status == TextureStatus.PROCESSING
        if self.error:
            raise self.error
        output = context.job_dir / "model_textured.glb"
        output.write_bytes(b"textured")
        return TextureResult(
            context.job_id,
            "completed",
            mesh,
            output,
            "model_textured.glb",
            "glb",
            {"size_bytes": output.stat().st_size},
        )


def task_and_jobs(tmp_path: Path):
    jobs = MemoryJobRepository()
    job_id = uuid4()
    job_dir = tmp_path / str(job_id)
    job_dir.mkdir()
    mesh = job_dir / "model.glb"
    mesh.write_bytes(b"white")
    image = job_dir / "robot.png"
    image.write_bytes(b"png")
    job = (
        Job.queued(job_id, "hunyuan")
        .transition(JobStatus.PROCESSING)
        .transition(JobStatus.COMPLETED, artifact_relative_path="model.glb")
    )
    jobs.save(job)
    task = TextureQueuedJob(
        job,
        JobContext(job_id, job_dir),
        mesh,
        image,
        TextureRequest(512, "fast"),
    )
    return jobs, task


def test_texture_cycle_stops_shape_paints_restarts_and_completes(tmp_path: Path):
    jobs, task = task_and_jobs(tmp_path)
    manager = Manager()
    lock = Lock()
    executor = TextureExecutor(
        jobs,
        Service(jobs, task.job.id),
        process_manager=manager,
        gpu_lock=lock,
        memory_probe=lambda: {"total_mib": 24576, "used_mib": 1, "free_mib": 24575},
    )

    executor.execute(task)

    stored = jobs.get(task.job.id)
    assert manager.calls == ["stop", "restart"]
    assert lock.entered == lock.exited == 1
    assert stored.status == JobStatus.COMPLETED
    assert stored.texture_status == TextureStatus.COMPLETED
    assert task.mesh_path.read_bytes() == b"white"


def test_texture_failure_restarts_shape_and_preserves_white_model(tmp_path: Path):
    jobs, task = task_and_jobs(tmp_path)
    manager = Manager()
    executor = TextureExecutor(
        jobs,
        Service(
            jobs,
            task.job.id,
            TexturePipelineError("paint", "Falha na etapa paint"),
        ),
        process_manager=manager,
        gpu_lock=Lock(),
        memory_probe=lambda: None,
    )

    with pytest.raises(TexturePipelineError, match="Falha na etapa paint"):
        executor.execute(task)

    stored = jobs.get(task.job.id)
    assert manager.calls == ["stop", "restart"]
    assert stored.status == JobStatus.COMPLETED
    assert stored.texture_status == TextureStatus.FAILED
    assert stored.texture_error == "Falha na etapa paint"
    assert task.mesh_path.read_bytes() == b"white"


def test_restart_failure_does_not_overwrite_primary_texture_error(tmp_path: Path):
    jobs, task = task_and_jobs(tmp_path)
    executor = TextureExecutor(
        jobs,
        Service(
            jobs,
            task.job.id,
            TexturePipelineError("paint", "Falha principal do Paint"),
        ),
        process_manager=Manager(RuntimeError("restart secret")),
        gpu_lock=Lock(),
        memory_probe=lambda: None,
    )

    with pytest.raises(TexturePipelineError, match="Falha principal do Paint"):
        executor.execute(task)

    stored = jobs.get(task.job.id)
    assert stored.texture_error == "Falha principal do Paint"
    assert (
        stored.texture_metadata["restart_error"] == "Falha ao reiniciar Hunyuan Shape"
    )
    assert "restart secret" not in str(stored.texture_metadata)
