from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import Container
from app.api.routes import downloads, generation, health
from app.core.config import Settings
from app.engines.policy import AutoEnginePolicy
from app.engines.registry import EngineRegistry
from app.infrastructure.hunyuan_gateway import GradioHunyuanGateway
from app.infrastructure.job_repository import JsonJobRepository
from app.infrastructure.storage import LocalStorage
from app.infrastructure.subprocess_runner import SubprocessRunner
from app.services.hunyuan import HunyuanService
from app.services.triposr import TripoSRService
from app.services.upload_validation import UploadValidator


def build_container(settings: Settings) -> Container:
    storage = LocalStorage(settings.upload_dir, settings.output_dir)
    jobs = JsonJobRepository(settings.jobs_file)
    registry = EngineRegistry()
    registry.register(TripoSRService(settings, SubprocessRunner()))
    registry.register(
        HunyuanService(
            settings,
            storage,
            GradioHunyuanGateway(settings.hunyuan_url),
        )
    )
    return Container(
        settings=settings,
        storage=storage,
        jobs=jobs,
        validator=UploadValidator(
            settings.allowed_image_types, settings.upload_max_bytes
        ),
        engines=registry,
        auto_policy=AutoEnginePolicy(
            registry,
            fallback=settings.auto_engine,
        ),
    )


def create_app(
    settings: Optional[Settings] = None,
    container: Optional[Container] = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_container = container or build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        resolved_container.storage.initialize()
        resolved_container.jobs.initialize()
        yield

    application = FastAPI(
        title="Forge3D AI API",
        version="0.3.0",
        lifespan=lifespan,
    )
    application.state.container = resolved_container
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(generation.router)
    application.include_router(downloads.router)
    return application


# Composition is lightweight: no model, process, remote client, or filesystem is
# initialized until application startup or an explicit generation request.
app = create_app()
