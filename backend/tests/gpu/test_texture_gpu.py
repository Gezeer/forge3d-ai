import os
import struct
import time

import httpx
import pytest

pytestmark = [
    pytest.mark.texture_gpu,
    pytest.mark.skipif(
        os.getenv("RUN_TEXTURE_GPU_TESTS") != "1", reason="texture GPU opt-in"
    ),
]


def test_real_hunyuan_texture_glb():
    api = os.environ["FORGE3D_TEST_API_URL"].rstrip("/")
    job_id = os.environ["FORGE3D_TEXTURE_TEST_JOB_ID"]
    timeout = float(os.getenv("FORGE3D_TEXTURE_TEST_TIMEOUT", "1800"))
    response = httpx.post(
        f"{api}/jobs/{job_id}/texture",
        data={"engine": "hunyuan", "quality": "standard", "resolution": 2048},
        timeout=30,
    )
    assert response.status_code == 202
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = httpx.get(f"{api}/jobs/{job_id}", timeout=30).json()
        if status.get("texture_status") in {"textured", "texture_failed"}:
            break
        time.sleep(3)
    assert status["texture_status"] == "textured"
    artifact = httpx.get(f"{api}/download/{job_id}/textured", timeout=120)
    assert artifact.status_code == 200
    assert len(artifact.content) > 20
    magic, version = struct.unpack("<4sI", artifact.content[:8])
    assert magic == b"glTF"
    assert version == 2
    metadata = status.get("texture_metadata") or {}
    assert metadata.get("size_bytes", 0) > 0
    assert (
        metadata.get("maps")
        or b"materials" in artifact.content.lower()
        or b"textures" in artifact.content.lower()
    )
