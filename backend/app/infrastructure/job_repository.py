from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Optional
from uuid import UUID

from app.domain.jobs import Job


class JsonJobRepository:
    """Small local repository implementing the replaceable JobRepository contract."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._jobs: Dict[UUID, Job] = {}
        self._lock = threading.RLock()

    def initialize(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                return
            payload = json.loads(self.path.read_text(encoding="utf-8") or "[]")
            self._jobs = {job.id: job for job in map(Job.from_dict, payload)}

    def save(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = job
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(
                    [item.to_dict() for item in self._jobs.values()],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        return job

    def get(self, job_id: UUID) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)


class MemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: Dict[UUID, Job] = {}

    def initialize(self) -> None:
        pass

    def save(self, job: Job) -> Job:
        self._jobs[job.id] = job
        return job

    def get(self, job_id: UUID) -> Optional[Job]:
        return self._jobs.get(job_id)
