from __future__ import annotations

import os
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


def _configuration() -> tuple[str, Path]:
    api_url = os.environ["FORGE3D_TEST_API_URL"].rstrip("/")
    image = Path(os.environ["FORGE3D_TEST_IMAGE"])
    assert image.is_file()
    return api_url, image


@pytest.mark.parametrize("engine", ["triposr", "hunyuan"])
def test_live_runpod_generation_and_download(engine: str) -> None:
    api_url, image = _configuration()
    with image.open("rb") as source:
        response = httpx.post(
            f"{api_url}/generate/{engine}",
            files={"file": (image.name, source, "image/png")},
            timeout=1200,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    download = httpx.get(f"{api_url}{body['download_url']}", timeout=120)
    assert download.status_code == 200
    assert len(download.content) > 0
