from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Protocol
from uuid import UUID


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Job:
    id: UUID
    engine: str
    status: JobStatus
    created_at: str
    updated_at: str
    artifact_relative_path: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def queued(cls, job_id: UUID, engine: str) -> "Job":
        now = utc_now()
        return cls(
            id=job_id,
            engine=engine,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )

    def transition(
        self,
        status: JobStatus,
        *,
        artifact_relative_path: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Job":
        allowed = {
            JobStatus.QUEUED: {JobStatus.PROCESSING, JobStatus.FAILED},
            JobStatus.PROCESSING: {JobStatus.COMPLETED, JobStatus.FAILED},
            JobStatus.COMPLETED: set(),
            JobStatus.FAILED: set(),
        }
        if status not in allowed[self.status]:
            raise ValueError(f"Invalid job transition: {self.status} -> {status}")
        return Job(
            id=self.id,
            engine=self.engine,
            status=status,
            created_at=self.created_at,
            updated_at=utc_now(),
            artifact_relative_path=artifact_relative_path,
            error=error,
            metadata=metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["id"] = str(self.id)
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Job":
        return cls(
            id=UUID(payload["id"]),
            engine=payload["engine"],
            status=JobStatus(payload["status"]),
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
            artifact_relative_path=payload.get("artifact_relative_path"),
            error=payload.get("error"),
            metadata=payload.get("metadata"),
        )


class JobRepository(Protocol):
    def initialize(self) -> None: ...

    def save(self, job: Job) -> Job: ...

    def get(self, job_id: UUID) -> Optional[Job]: ...
