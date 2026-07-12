from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings
from app.domain.jobs import JobRepository
from app.infrastructure.storage import LocalStorage
from app.services.hunyuan import HunyuanService
from app.services.triposr import TripoSRService
from app.services.upload_validation import UploadValidator


@dataclass
class Container:
    settings: Settings
    storage: LocalStorage
    jobs: JobRepository
    validator: UploadValidator
    triposr: TripoSRService
    hunyuan: HunyuanService


def get_container(request: Request) -> Container:
    return request.app.state.container
