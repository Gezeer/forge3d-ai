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


class TextureStatus(str, Enum):
    QUEUED = "texture_queued"
    PROCESSING = "texturing"
    COMPLETED = "textured"
    FAILED = "texture_failed"


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
    texture_status: Optional[TextureStatus] = None
    texture_artifact_relative_path: Optional[str] = None
    output_textured_glb: Optional[str] = None
    texture_error: Optional[str] = None
    texture_metadata: Optional[Dict[str, Any]] = None

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
            texture_status=self.texture_status,
            texture_artifact_relative_path=self.texture_artifact_relative_path,
            output_textured_glb=self.output_textured_glb,
            texture_error=self.texture_error,
            texture_metadata=self.texture_metadata,
        )

    def transition_texture(
        self,
        status: TextureStatus,
        *,
        artifact_relative_path: Optional[str] = None,
        output_textured_glb: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Job":
        allowed = {
            None: {TextureStatus.QUEUED},
            TextureStatus.QUEUED: {TextureStatus.PROCESSING, TextureStatus.FAILED},
            TextureStatus.PROCESSING: {TextureStatus.COMPLETED, TextureStatus.FAILED},
            TextureStatus.COMPLETED: {TextureStatus.QUEUED},
            TextureStatus.FAILED: {TextureStatus.QUEUED},
        }
        if status not in allowed[self.texture_status]:
            raise ValueError(
                f"Invalid texture transition: {self.texture_status} -> {status}"
            )
        return Job(
            id=self.id,
            engine=self.engine,
            status=self.status,
            created_at=self.created_at,
            updated_at=utc_now(),
            artifact_relative_path=self.artifact_relative_path,
            error=self.error,
            metadata=self.metadata,
            texture_status=status,
            texture_artifact_relative_path=artifact_relative_path,
            output_textured_glb=output_textured_glb or self.output_textured_glb,
            texture_error=error,
            texture_metadata=metadata,
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
            texture_status=TextureStatus(payload["texture_status"])
            if payload.get("texture_status")
            else None,
            texture_artifact_relative_path=payload.get(
                "texture_artifact_relative_path"
            ),
            output_textured_glb=payload.get("output_textured_glb"),
            texture_error=payload.get("texture_error"),
            texture_metadata=payload.get("texture_metadata"),
        )


class JobRepository(Protocol):
    def initialize(self) -> None: ...

    def save(self, job: Job) -> Job: ...

    def get(self, job_id: UUID) -> Optional[Job]: ...
