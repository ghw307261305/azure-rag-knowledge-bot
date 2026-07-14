import json
import logging

from app.services.logging_service import JsonFormatter, reset_request_id, set_request_id


def test_json_formatter_includes_request_context_without_payload() -> None:
    token = set_request_id("request-123")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="HTTP request completed",
            args=(),
            exc_info=None,
        )
        record.event = "http_request"
        record.method = "POST"
        record.path = "/api/chat"
        record.status_code = 200
        record.latency_ms = 12.5

        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["request_id"] == "request-123"
    assert payload["path"] == "/api/chat"
    assert payload["status_code"] == 200
    assert "question" not in payload
