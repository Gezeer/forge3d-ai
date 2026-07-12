import json
import logging

from app.observability.logging import JsonFormatter


def test_json_log_has_structured_generation_fields_without_secrets():
    record = logging.LogRecord(
        "forge3d.jobs", logging.INFO, __file__, 1, "job completed", (), None
    )
    record.request_id = "request"
    record.job_id = "job"
    record.engine = "triposr"
    record.status = "completed"
    record.duration_ms = 12.5
    record.error_code = ""

    payload = json.loads(JsonFormatter().format(record))

    assert payload["job_id"] == "job"
    assert payload["engine"] == "triposr"
    assert payload["duration_ms"] == 12.5
    assert "token" not in payload
    assert "stderr" not in payload
