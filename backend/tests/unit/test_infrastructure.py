import subprocess
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.core.exceptions import GenerationTimeoutError, InvalidUploadError
from app.infrastructure.storage import LocalStorage
from app.infrastructure.subprocess_runner import SubprocessRunner
from app.services.upload_validation import UploadValidator


def test_settings_keep_runpod_defaults() -> None:
    settings = Settings.from_env({})

    assert str(settings.triposr_run) == "/workspace/kai3d/models/TripoSR/run.py"
    assert settings.triposr_device == "cuda:0"
    assert settings.hunyuan_url == "http://127.0.0.1:8080"
    assert settings.hunyuan_endpoint == "/run/shape_generation"
    assert settings.hunyuan_retry_attempts == 5
    assert settings.health_timeout_seconds == 10
    assert "proxy\\.runpod\\.net" in settings.cors_origin_regex


def test_settings_can_be_overridden() -> None:
    settings = Settings.from_env(
        {
            "FORGE3D_OUTPUT_DIR": "/tmp/custom-output",
            "FORGE3D_TRIPOSR_DEVICE": "cuda:1",
            "FORGE3D_CORS_ORIGINS": "https://one.test,https://two.test",
            "FORGE3D_CORS_ORIGIN_REGEX": "^https://pod.test$",
            "FORGE3D_QUEUE_CONCURRENCY": "3",
            "FORGE3D_QUEUE_MAX_SIZE": "25",
            "FORGE3D_DEFAULT_ENGINE": "hunyuan",
            "FORGE3D_HUNYUAN_ENDPOINT": "/run/custom_shape",
            "FORGE3D_HUNYUAN_RETRY_ATTEMPTS": "3",
            "FORGE3D_AUTO_ENGINE_FALLBACK": "triposr",
        }
    )

    assert settings.output_dir == Path("/tmp/custom-output")
    assert settings.jobs_file == Path("/tmp/custom-output/jobs.json")
    assert settings.triposr_device == "cuda:1"
    assert settings.cors_origins == ("https://one.test", "https://two.test")
    assert settings.cors_origin_regex == "^https://pod.test$"
    assert settings.queue_concurrency == 3
    assert settings.queue_max_size == 25
    assert settings.default_engine == "hunyuan"
    assert settings.hunyuan_endpoint == "/run/custom_shape"
    assert settings.hunyuan_retry_attempts == 3
    assert settings.auto_engine_fallback == "triposr"


@pytest.mark.parametrize(
    ("unsafe", "safe"),
    [("../../secret.png", "secret.png"), ("..\\secret.png", "secret.png")],
)
def test_storage_sanitizes_traversal_names(unsafe: str, safe: str) -> None:
    assert LocalStorage.safe_filename(unsafe) == safe


def test_saved_upload_stays_inside_job_directory(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "uploads", tmp_path / "outputs")
    storage.initialize()
    job_dir = storage.create_job_dir(uuid4())

    saved = storage.save_upload(job_dir, "../../../image.png", BytesIO(b"image"))

    assert saved == job_dir / "image.png"
    assert saved.read_bytes() == b"image"


def test_upload_validator_rejects_type_and_size() -> None:
    validator = UploadValidator(["image/png"], max_bytes=4)

    with pytest.raises(InvalidUploadError, match="Tipo"):
        validator.validate_metadata("text/plain")
    with pytest.raises(InvalidUploadError, match="limite"):
        validator.validate_size(BytesIO(b"12345"))


def test_subprocess_runner_maps_timeout(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)

    with pytest.raises(GenerationTimeoutError, match="tempo limite"):
        SubprocessRunner().run(["generator"], timeout=1)
