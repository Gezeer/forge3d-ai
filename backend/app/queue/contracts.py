from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.domain.jobs import Job
from app.engines.contracts import JobContext


@dataclass(frozen=True)
class QueuedJob:
    job: Job
    context: JobContext
    image_path: Path


class JobQueue(Protocol):
    def start(self) -> None:
        ...

    def enqueue(self, task: QueuedJob) -> None:
        ...

    def stop(self) -> None:
        ...
