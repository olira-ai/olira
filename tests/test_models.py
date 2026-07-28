"""Tests for SDK models."""

import pytest
from pydantic import ValidationError

from olira.models import LogsResult, OliraTrace, _LogWire


def test_default_base_url():
    from olira import DEFAULT_BASE_URL

    assert DEFAULT_BASE_URL == "https://app-api.prod.olira.ai/app-api"


def test_logs_result_accepts_null_trace_fields():
    result = LogsResult.model_validate(
        {
            "patient_id": "p_123",
            "count": 2,
            "logs": [
                {
                    "id": "log_1",
                    "type": "symptom_report",
                    "timestamp": "2026-03-18T10:00:00+00:00",
                    "payload": {},
                    "trace": {"object_type": "conversation", "object_id": "conv-abc"},
                },
                {
                    "id": "log_2",
                    "type": "user_login",
                    "timestamp": "2026-03-18T10:01:00+00:00",
                    "payload": {},
                    "trace": {"object_type": None, "object_id": None},
                },
            ],
        }
    )
    assert result.count == 2
    assert result.logs[1].trace is not None
    assert result.logs[1].trace.object_type is None
    assert result.logs[1].trace.object_id is None


def test_logs_result_parses_ingested_at():
    result = LogsResult.model_validate(
        {
            "patient_id": "p_123",
            "count": 1,
            "logs": [
                {
                    "id": "log_1",
                    "type": "symptom_report",
                    "timestamp": "2026-03-18T10:00:00+00:00",
                    "ingested_at": "2026-03-18T10:00:05+00:00",
                    "payload": {},
                },
            ],
        }
    )
    assert result.logs[0].ingested_at == "2026-03-18T10:00:05+00:00"


def test_logs_result_ingested_at_defaults_to_none():
    result = LogsResult.model_validate(
        {
            "patient_id": "p_123",
            "count": 1,
            "logs": [{"id": "log_1", "type": "symptom_report", "timestamp": "2026-03-18T10:00:00+00:00", "payload": {}}],
        }
    )
    assert result.logs[0].ingested_at is None


def test_log_wire_requires_complete_trace():
    with pytest.raises(ValidationError, match="trace requires both object_type and object_id"):
        _LogWire(
            log_type="conversation_completed",
            patient_id="p_abc",
            context={"environment": "production", "service": "", "sdk_version": "0.1.0", "sdk_language": "python"},
            trace=OliraTrace(object_type=None, object_id="conv_789"),
        )


def test_log_wire_accepts_complete_trace():
    wire = _LogWire(
        log_type="conversation_completed",
        patient_id="p_abc",
        context={"environment": "production", "service": "", "sdk_version": "0.1.0", "sdk_language": "python"},
        trace=OliraTrace(object_type="conversation", object_id="conv_789"),
    )
    assert wire.trace is not None
    assert wire.trace.object_type == "conversation"
