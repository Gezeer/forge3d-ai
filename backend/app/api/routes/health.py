import os
import queue
import threading

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import Container, get_container
from app.api.schemas import HealthResponse
from app.engines.contracts import EngineHealth

router = APIRouter(tags=["system"])


def _health_with_timeout(engine, timeout: float) -> EngineHealth:
    results = queue.Queue(maxsize=1)

    def probe():
        try:
            results.put(engine.health())
        except Exception:
            results.put(EngineHealth(engine.name, False, {"probe": "failed"}))

    threading.Thread(target=probe, daemon=True).start()
    try:
        return results.get(timeout=timeout)
    except queue.Empty:
        return EngineHealth(engine.name, False, {"probe": "timeout"})


@router.get("/", include_in_schema=False)
def home() -> dict:
    return {"name": "Forge3D AI", "status": "running", "version": "0.3.0"}


def _snapshot(container: Container) -> HealthResponse:
    settings = container.settings
    engine_health = [
        _health_with_timeout(engine, settings.health_timeout_seconds)
        for engine in container.engines.list()
    ]
    storage_ok = (
        settings.upload_dir.is_dir()
        and settings.output_dir.is_dir()
        and os.access(settings.output_dir, os.W_OK)
    )
    repository_ok = settings.jobs_file.parent.is_dir()
    queue_ok = container.job_queue.started
    any_engine = any(item.available for item in engine_health)
    infrastructure_ok = storage_ok and repository_ok and queue_ok
    if not infrastructure_ok or not any_engine:
        overall = "unhealthy"
    elif not all(item.available for item in engine_health):
        overall = "degraded"
    else:
        overall = "healthy"
    engines = {}
    for item in engine_health:
        configured = bool(item.details.get("configured", True))
        engines[item.name] = {
            "configured": configured,
            "available": item.available,
            "status": "healthy" if item.available else "unavailable",
            "details": item.details,
        }
    return HealthResponse(
        api="ok",
        triposr_run_exists=settings.triposr_run.exists(),
        hunyuan_configured=bool(settings.hunyuan_signature_json.strip()),
        upload_dir=str(settings.upload_dir),
        output_dir=str(settings.output_dir),
        engines=engines,
        status=overall,
        queue={
            "status": "ready" if queue_ok else "stopped",
            "size": container.job_queue.size,
            "capacity": container.job_queue.max_size,
            "workers": container.job_queue.workers_alive,
        },
        job_repository={"status": "healthy" if repository_ok else "unhealthy"},
        storage={"status": "healthy" if storage_ok else "unhealthy"},
        version="0.3.0",
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Saúde operacional",
    description="Preserva os campos legados e adiciona estado dos componentes.",
)
def health(container: Container = Depends(get_container)) -> HealthResponse:
    return _snapshot(container)


@router.get("/health/live", summary="Liveness do processo")
def live() -> dict:
    return {"status": "alive", "version": "0.3.0"}


@router.get("/health/ready", summary="Prontidão para aceitar jobs")
def ready(container: Container = Depends(get_container)):
    snapshot = _snapshot(container)
    ready_status = snapshot.status in {"healthy", "degraded"}
    return JSONResponse(
        status_code=200 if ready_status else 503,
        content={"status": "ready" if ready_status else "not_ready"},
    )
