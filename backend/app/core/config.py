from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Tuple


def _csv(value: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    upload_dir: Path = Path("/workspace/forge3d-ai/uploads")
    output_dir: Path = Path("/workspace/forge3d-ai/outputs")
    triposr_run: Path = Path("/workspace/kai3d/models/TripoSR/run.py")
    triposr_python: Path = Path(
        "/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python"
    )
    triposr_device: str = "cuda:0"
    hunyuan_url: str = "http://127.0.0.1:8080"
    hunyuan_api_name: str = "/generation_all"
    hunyuan_signature_json: str = ""
    generation_timeout_seconds: float = 900.0
    upload_max_bytes: int = 20 * 1024 * 1024
    allowed_image_types: Tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
    )
    cors_origins: Tuple[str, ...] = ("http://localhost:3000",)
    environment: str = "development"
    jobs_file: Path = Path("/workspace/forge3d-ai/outputs/jobs.json")
    auto_engine: str = "triposr"
    queue_concurrency: int = 1
    queue_max_size: int = 100
    default_engine: str = "auto"
    auto_engine_fallback: str = "triposr"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "Settings":
        output_dir = Path(
            environ.get("FORGE3D_OUTPUT_DIR", "/workspace/forge3d-ai/outputs")
        )
        return cls(
            upload_dir=Path(
                environ.get("FORGE3D_UPLOAD_DIR", "/workspace/forge3d-ai/uploads")
            ),
            output_dir=output_dir,
            triposr_run=Path(
                environ.get(
                    "FORGE3D_TRIPOSR_RUN",
                    "/workspace/kai3d/models/TripoSR/run.py",
                )
            ),
            triposr_python=Path(
                environ.get(
                    "FORGE3D_TRIPOSR_PYTHON",
                    "/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python",
                )
            ),
            triposr_device=environ.get("FORGE3D_TRIPOSR_DEVICE", "cuda:0"),
            hunyuan_url=environ.get("FORGE3D_HUNYUAN_URL", "http://127.0.0.1:8080"),
            hunyuan_api_name=environ.get(
                "FORGE3D_HUNYUAN_API_NAME", "/generation_all"
            ),
            hunyuan_signature_json=environ.get(
                "FORGE3D_HUNYUAN_SIGNATURE_JSON", ""
            ),
            generation_timeout_seconds=float(
                environ.get("FORGE3D_GENERATION_TIMEOUT_SECONDS", "900")
            ),
            upload_max_bytes=int(
                environ.get("FORGE3D_UPLOAD_MAX_BYTES", str(20 * 1024 * 1024))
            ),
            allowed_image_types=_csv(
                environ.get(
                    "FORGE3D_ALLOWED_IMAGE_TYPES",
                    "image/jpeg,image/png,image/webp",
                )
            ),
            cors_origins=_csv(
                environ.get("FORGE3D_CORS_ORIGINS", "http://localhost:3000")
            ),
            environment=environ.get("FORGE3D_ENV", "development"),
            jobs_file=Path(
                environ.get("FORGE3D_JOBS_FILE", str(output_dir / "jobs.json"))
            ),
            auto_engine=environ.get("FORGE3D_AUTO_ENGINE", "triposr"),
            queue_concurrency=int(
                environ.get("FORGE3D_QUEUE_CONCURRENCY", "1")
            ),
            queue_max_size=int(environ.get("FORGE3D_QUEUE_MAX_SIZE", "100")),
            default_engine=environ.get("FORGE3D_DEFAULT_ENGINE", "auto"),
            auto_engine_fallback=environ.get(
                "FORGE3D_AUTO_ENGINE_FALLBACK", "triposr"
            ),
        )

    @property
    def expose_process_details(self) -> bool:
        return self.environment.lower() not in {"production", "prod"}
