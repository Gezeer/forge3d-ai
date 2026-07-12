from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
import pytest

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(
        os.getenv("RUN_GPU_TESTS") != "1",
        reason="GPU tests require explicit RUN_GPU_TESTS=1 on RunPod",
    ),
]
FORMATS = {".glb", ".obj", ".ply", ".stl"}


def _configuration() -> tuple[str, Path, Path, float]:
    api_url = os.environ["FORGE3D_TEST_API_URL"].rstrip("/")
    image = Path(os.environ["FORGE3D_TEST_IMAGE"])
    output_dir = Path(os.getenv("FORGE3D_OUTPUT_DIR", "/workspace/forge3d-ai/outputs"))
    timeout = float(os.getenv("FORGE3D_GPU_TEST_TIMEOUT", "1200"))
    assert image.is_file(), "FORGE3D_TEST_IMAGE não existe"
    return api_url, image, output_dir, timeout


def _safe_error(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
        return f"status={response.status_code} code={error.get('code', 'unknown')}"
    except Exception:
        return f"status={response.status_code} non_json_response"


def _physical_artifact(output_dir: Path, job_id: str) -> Path:
    candidates = [
        path
        for path in (output_dir / job_id).rglob("*")
        if path.is_file() and path.suffix.lower() in FORMATS and path.stat().st_size > 0
    ]
    assert candidates, f"artifact_missing job_id={job_id}"
    return candidates[0]


def _download(api_url: str, body: dict, timeout: float) -> bytes:
    response = httpx.get(f"{api_url}{body['download_url']}", timeout=timeout)
    assert response.status_code == 200, _safe_error(response)
    assert len(response.content) > 0
    return response.content


def test_health_reports_hunyuan_available() -> None:
    api_url, _, _, timeout = _configuration()
    response = httpx.get(f"{api_url}/health", timeout=min(timeout, 15))
    assert response.status_code == 200, _safe_error(response)
    hunyuan = response.json()["engines"]["hunyuan"]
    assert hunyuan["configured"] is True
    assert hunyuan["available"] is True
    assert hunyuan["details"]["api_name"] == "/shape_generation"


def test_live_hunyuan_sync_generation_and_download() -> None:
    api_url, image, output_dir, timeout = _configuration()
    with image.open("rb") as source:
        response = httpx.post(
            f"{api_url}/generate/hunyuan",
            files={"file": (image.name, source, "image/png")},
            timeout=timeout,
        )
    assert response.status_code == 200, _safe_error(response)
    body = response.json()
    artifact = _physical_artifact(output_dir, body["job_id"])
    assert artifact.suffix.lower() in FORMATS
    assert len(_download(api_url, body, timeout)) > 0


def test_live_hunyuan_queued_generation() -> None:
    api_url, image, output_dir, timeout = _configuration()
    with image.open("rb") as source:
        response = httpx.post(
            f"{api_url}/jobs/generate",
            data={"engine": "hunyuan"},
            files={"file": (image.name, source, "image/png")},
            timeout=30,
        )
    assert response.status_code == 202, _safe_error(response)
    queued = response.json()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = httpx.get(f"{api_url}{queued['status_url']}", timeout=30)
        assert status.status_code == 200, _safe_error(status)
        body = status.json()
        if body["status"] in {"completed", "failed"}:
            break
        time.sleep(2)
    else:
        pytest.fail(f"queue_timeout job_id={queued['job_id']}")
    assert body["status"] == "completed", f"job_failed error={body.get('error')}"
    _physical_artifact(output_dir, queued["job_id"])
    assert len(_download(api_url, body, timeout)) > 0


def test_live_triposr_legacy_contract() -> None:
    api_url, image, output_dir, timeout = _configuration()
    with image.open("rb") as source:
        response = httpx.post(
            f"{api_url}/generate/image",
            files={"file": (image.name, source, "image/png")},
            timeout=timeout,
        )
    assert response.status_code == 200, _safe_error(response)
    body = response.json()
    artifact = output_dir / body["job_id"] / "0" / "mesh.glb"
    assert artifact.is_file() and artifact.stat().st_size > 0
    assert len(_download(api_url, body, timeout)) > 0
