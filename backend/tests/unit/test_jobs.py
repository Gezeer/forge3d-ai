from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.jobs import Job, JobStatus
from app.infrastructure.job_repository import JsonJobRepository


def test_job_state_machine() -> None:
    job = Job.queued(uuid4(), "triposr")
    assert job.status == JobStatus.QUEUED
    job = job.transition(JobStatus.PROCESSING)
    assert job.status == JobStatus.PROCESSING
    job = job.transition(
        JobStatus.COMPLETED, artifact_relative_path="0/mesh.glb"
    )
    assert job.status == JobStatus.COMPLETED

    with pytest.raises(ValueError):
        job.transition(JobStatus.PROCESSING)


def test_json_repository_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    repository = JsonJobRepository(path)
    repository.initialize()
    job = Job.queued(uuid4(), "hunyuan")
    repository.save(job)

    reloaded = JsonJobRepository(path)
    reloaded.initialize()

    assert reloaded.get(job.id) == job
