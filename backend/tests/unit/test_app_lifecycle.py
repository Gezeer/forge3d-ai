from pathlib import Path

from app.core.config import Settings
from app.main import build_container, create_app
from fastapi.testclient import TestClient


def test_building_application_does_not_start_queue_workers(tmp_path: Path) -> None:
    settings = Settings(
        upload_dir=tmp_path / "uploads",
        output_dir=tmp_path / "outputs",
        jobs_file=tmp_path / "outputs" / "jobs.json",
        queue_concurrency=2,
    )

    container = build_container(settings)
    app = create_app(settings, container)

    assert container.job_queue.started is False
    assert container.job_queue.workers_alive == 0

    with TestClient(app):
        assert container.job_queue.started is True
        assert container.job_queue.workers_alive == 2

    assert container.job_queue.started is False
    assert container.job_queue.workers_alive == 0
