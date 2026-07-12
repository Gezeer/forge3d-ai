from fastapi import APIRouter, Depends

from app.api.dependencies import Container, get_container
from app.api.schemas import HealthResponse


router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
def home() -> dict:
    return {"name": "Forge3D AI", "status": "running", "version": "0.3.0"}


@router.get("/health", response_model=HealthResponse)
def health(container: Container = Depends(get_container)) -> HealthResponse:
    settings = container.settings
    return HealthResponse(
        api="ok",
        triposr_run_exists=settings.triposr_run.exists(),
        hunyuan_configured=bool(settings.hunyuan_signature_json.strip()),
        upload_dir=str(settings.upload_dir),
        output_dir=str(settings.output_dir),
    )
