from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings
from app.domain.jobs import JobRepository
from app.engines.policy import AutoEnginePolicy
from app.engines.registry import EngineRegistry
from app.infrastructure.storage import LocalStorage
from app.observability.metrics import MetricsRegistry
from app.queue.contracts import JobQueue
from app.queue.executor import JobExecutor
from app.services.upload_validation import UploadValidator


@dataclass
class Container:
    settings: Settings
    storage: LocalStorage
    jobs: JobRepository
    validator: UploadValidator
    engines: EngineRegistry
    auto_policy: AutoEnginePolicy
    executor: JobExecutor
    job_queue: JobQueue
    metrics: MetricsRegistry


def get_container(request: Request) -> Container:
    return request.app.state.container
