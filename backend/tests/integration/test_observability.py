from uuid import uuid4

from app.core.exceptions import GenerationError
from test_api import FakeGenerator, _client


def test_request_id_is_generated_and_returned(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert str(uuid4()).__len__() == len(response.headers["X-Request-ID"])


def test_valid_received_request_id_is_returned(tmp_path):
    client, _ = _client(tmp_path)
    request_id = str(uuid4())
    with client:
        response = client.get("/health/live", headers={"X-Request-ID": request_id})
    assert response.headers["X-Request-ID"] == request_id


def test_error_has_standard_shape_and_request_header(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        response = client.get("/jobs/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_health_preserves_legacy_fields_and_degrades_for_hunyuan(tmp_path):
    client, _ = _client(tmp_path, hunyuan=FakeGenerator("hunyuan", available=False))
    with client:
        body = client.get("/health").json()
    assert {"api", "triposr_run_exists", "upload_dir", "output_dir"} <= body.keys()
    assert body["status"] == "degraded"
    assert body["engines"]["hunyuan"]["available"] is False


def test_health_reports_hunyuan_paused_for_texture_without_failing_api(tmp_path):
    client, container = _client(
        tmp_path, hunyuan=FakeGenerator("hunyuan", available=False)
    )

    class ManagedState:
        operational_state = "paused_for_texture"

    manager = ManagedState()
    container.hunyuan_process_manager = manager
    with client:
        paused = client.get("/health").json()
        manager.operational_state = "restarting"
        restarting = client.get("/health").json()

    assert paused["engines"]["hunyuan"]["status"] == "paused_for_texture"
    assert paused["status"] == "degraded"
    assert restarting["engines"]["hunyuan"]["status"] == "restarting"
    assert restarting["status"] == "degraded"


def test_live_does_not_call_engines(tmp_path):
    client, container = _client(tmp_path)

    class BombEngine(FakeGenerator):
        def health(self):
            raise AssertionError("live called engine")

        def available(self):
            raise AssertionError("live called engine")

    container.engines._engines["hunyuan"] = BombEngine("hunyuan")
    with client:
        response = client.get("/health/live")
    assert response.status_code == 200


def test_ready_returns_200_and_503(tmp_path):
    ready_client, _ = _client(tmp_path)
    unavailable_client, _ = _client(
        tmp_path / "unavailable",
        triposr=FakeGenerator("triposr", available=False),
        hunyuan=FakeGenerator("hunyuan", available=False),
    )
    with ready_client:
        assert ready_client.get("/health/ready").status_code == 200
    with unavailable_client:
        assert unavailable_client.get("/health/ready").status_code == 503


def test_metrics_enabled_include_jobs_queue_without_high_cardinality(tmp_path):
    client, _ = _client(tmp_path)
    with client:
        generated = client.post(
            "/generate/image",
            files={"file": ("secret-file.png", b"png", "image/png")},
        ).json()
        metrics = client.get("/metrics")
    assert metrics.status_code == 200
    text = metrics.text
    assert "forge3d_http_requests_total" in text
    assert 'forge3d_jobs_total{engine="triposr",status="completed"}' in text
    assert "forge3d_queue_size" in text
    assert generated["job_id"] not in text
    assert "secret-file.png" not in text
    assert "request_id=" not in text


def test_metrics_can_be_disabled(tmp_path):
    client, _ = _client(tmp_path, metrics_enabled=False)
    with client:
        response = client.get("/metrics")
    assert response.status_code == 404


def test_metrics_count_failed_jobs(tmp_path):
    client, _ = _client(
        tmp_path,
        triposr=FakeGenerator("triposr", error=GenerationError("failed")),
    )
    with client:
        response = client.post(
            "/generate/image",
            files={"file": ("image.png", b"png", "image/png")},
        )
        metrics = client.get("/metrics").text
    assert response.status_code == 500
    assert 'forge3d_jobs_total{engine="triposr",status="failed"}' in metrics


def test_openapi_contains_operational_endpoints(tmp_path):
    client, _ = _client(tmp_path)
    schema = client.app.openapi()
    assert {"/metrics", "/health/live", "/health/ready", "/jobs/generate"} <= set(
        schema["paths"]
    )
