import json
import logging

from app.core.config import Settings
from app.observability.logging import JsonFormatter, configure_logging


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


def test_configured_file_log_is_written_and_flushed(tmp_path):
    path = tmp_path / "forge3d-api.log"
    configure_logging(Settings(api_log=path))

    logging.getLogger("forge3d.hunyuan.process").error("critical restart diagnostic")

    assert "critical restart diagnostic" in path.read_text(encoding="utf-8")
