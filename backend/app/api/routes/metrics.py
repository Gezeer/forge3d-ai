from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.api.dependencies import Container, get_container

router = APIRouter(tags=["operations"])


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Métricas Prometheus",
    description="Expõe métricas sem labels de alta cardinalidade.",
)
def metrics(container: Container = Depends(get_container)) -> PlainTextResponse:
    if not container.metrics.enabled:
        raise HTTPException(status_code=404, detail="Métricas desativadas")
    return PlainTextResponse(
        container.metrics.render(container),
        media_type="text/plain; version=0.0.4",
    )
