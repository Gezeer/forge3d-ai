from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import Container
from app.api.handlers.errors import install_error_handlers
from app.api.routes import downloads, generation, health, metrics, texture
from app.core.config import Settings
from app.engines.policy import AutoEnginePolicy
from app.engines.registry import EngineRegistry
from app.infrastructure.hunyuan_gateway import GradioHunyuanGateway
from app.infrastructure.job_repository import JsonJobRepository
from app.infrastructure.storage import LocalStorage
from app.infrastructure.subprocess_runner import SubprocessRunner
from app.middleware.request_context import RequestContextMiddleware
from app.observability.logging import configure_logging
from app.observability.metrics import MetricsRegistry
from app.queue.executor import JobExecutor
from app.queue.local import LocalJobQueue
from app.services.hunyuan import HunyuanService
from app.services.triposr import TripoSRService
from app.services.upload_validation import UploadValidator
from app.texture.executor import TextureExecutor
from app.texture.hunyuan import HunyuanTextureService


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
    metrics_registry = MetricsRegistry(settings.metrics_enabled)
    executor = JobExecutor(jobs, registry, metrics_registry)
    texture_service = HunyuanTextureService(settings, SubprocessRunner())
    texture_executor = TextureExecutor(jobs, texture_service)
    job_queue = LocalJobQueue(
        executor,
        jobs,
        concurrency=settings.queue_concurrency,
        max_size=settings.queue_max_size,
        texture_executor=texture_executor,
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
            fallback=settings.auto_engine_fallback,
        ),
        executor=executor,
        job_queue=job_queue,
        metrics=metrics_registry,
    )


def create_app(
    settings: Optional[Settings] = None,
    container: Optional[Container] = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    configure_logging(resolved_settings)
    resolved_container = container or build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        resolved_container.storage.initialize()
        resolved_container.jobs.initialize()
        resolved_container.job_queue.start()
        try:
            yield
        finally:
            resolved_container.job_queue.stop()

    application = FastAPI(
        title="Forge3D AI API",
        version="0.3.0",
        lifespan=lifespan,
    )
    application.state.container = resolved_container
    application.state.metrics = resolved_container.metrics
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_origin_regex=resolved_settings.cors_origin_regex or None,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(generation.router)
    application.include_router(downloads.router)
    application.include_router(metrics.router)
    application.include_router(texture.router)
    install_error_handlers(application)
    return application


# Composition is lightweight: no model, process, remote client, or filesystem is
# initialized until application startup or an explicit generation request.
app = create_app()
