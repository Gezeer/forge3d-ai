from __future__ import annotations

import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.exceptions import JobQueueFullError
from app.domain.generation import GenerationResult
from app.domain.jobs import Job, JobStatus
from app.engines.contracts import EngineHealth, JobContext
from app.engines.registry import EngineRegistry
from app.infrastructure.job_repository import MemoryJobRepository
from app.queue.contracts import QueuedJob
from app.queue.executor import JobExecutor
from app.queue.local import LocalJobQueue


class RecordingEngine:
    name = "triposr"

    def __init__(self, *, fail_calls=None, barrier=None) -> None:
        self.calls = 0
        self.fail_calls = set(fail_calls or [])
        self.barrier = barrier
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def available(self):
        return True

    def health(self):
        return EngineHealth(self.name, True, {})

    def generate(self, context, image_path):
        self.calls += 1
        call = self.calls
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.barrier is not None:
                self.barrier.wait(timeout=2)
            if call in self.fail_calls:
                raise RuntimeError(f"failure {call}")
            artifact = context.job_dir / "0" / "mesh.glb"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"glb")
            return GenerationResult(
                context.job_id,
                self.name,
                artifact,
                "0/mesh.glb",
            )
        finally:
            with self.lock:
                self.active -= 1


def _task(tmp_path: Path, engine="triposr") -> QueuedJob:
    job_id = uuid4()
    job_dir = tmp_path / str(job_id)
    job_dir.mkdir()
    image = job_dir / "image.png"
    image.write_bytes(b"png")
    return QueuedJob(
        Job.queued(job_id, engine),
        JobContext(job_id, job_dir),
        image,
    )


def _queue(tmp_path: Path, engine, concurrency=1, max_size=10):
    jobs = MemoryJobRepository()
    registry = EngineRegistry()
    registry.register(engine)
    executor = JobExecutor(jobs, registry)
    return (
        LocalJobQueue(executor, jobs, concurrency, max_size),
        jobs,
    )


def test_enqueue_and_transitions_to_completed(tmp_path: Path) -> None:
    queue, jobs = _queue(tmp_path, RecordingEngine())
    task = _task(tmp_path)
    queue.start()

    queue.enqueue(task)
    queue.stop()

    completed = jobs.get(task.job.id)
    assert completed.status == JobStatus.COMPLETED
    assert completed.artifact_relative_path == "0/mesh.glb"
    assert queue.workers_alive == 0
    assert queue.started is False


def test_full_queue_is_normalized(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path, RecordingEngine(), max_size=1)
    queue.enqueue(_task(tmp_path))

    with pytest.raises(JobQueueFullError, match="fila local está cheia"):
        queue.enqueue(_task(tmp_path))


def test_failure_does_not_kill_worker_or_next_job(tmp_path: Path) -> None:
    engine = RecordingEngine(fail_calls={1})
    queue, jobs = _queue(tmp_path, engine)
    failed = _task(tmp_path)
    completed = _task(tmp_path)
    queue.start()

    queue.enqueue(failed)
    queue.enqueue(completed)
    queue.stop()

    assert jobs.get(failed.job.id).status == JobStatus.FAILED
    assert "RuntimeError: failure 1" in jobs.get(failed.job.id).error
    assert jobs.get(completed.job.id).status == JobStatus.COMPLETED
    assert engine.calls == 2


def test_configured_concurrency_runs_multiple_jobs(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    engine = RecordingEngine(barrier=barrier)
    queue, jobs = _queue(tmp_path, engine, concurrency=2)
    first = _task(tmp_path)
    second = _task(tmp_path)
    queue.start()

    queue.enqueue(first)
    queue.enqueue(second)
    queue.stop()

    assert engine.max_active == 2
    assert jobs.get(first.job.id).status == JobStatus.COMPLETED
    assert jobs.get(second.job.id).status == JobStatus.COMPLETED


def test_start_and_stop_are_idempotent_and_clean(tmp_path: Path) -> None:
    queue, _ = _queue(tmp_path, RecordingEngine(), concurrency=2)

    queue.start()
    queue.start()
    assert queue.workers_alive == 2
    queue.stop()
    queue.stop()

    assert queue.workers_alive == 0
