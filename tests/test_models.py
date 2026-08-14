"""Tests for SDK models."""

import pytest

from olira.exceptions import ValidationError
from olira.models import (
    RECOMMENDED_DIGEST_TRIGGERS,
    ActionDelivery,
    ActionDeliveryListResult,
    ActionDestination,
    ActionTrigger,
    CreatePatientRequest,
    DigestSchedule,
    LogsResult,
    OliraTrace,
    _LogWire,
)


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
            "logs": [
                {"id": "log_1", "type": "symptom_report", "timestamp": "2026-03-18T10:00:00+00:00", "payload": {}}
            ],
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


def test_create_patient_request_requires_anchor_field():
    with pytest.raises(ValidationError, match="at least one of"):
        CreatePatientRequest()


def test_log_wire_accepts_complete_trace():
    wire = _LogWire(
        log_type="conversation_completed",
        patient_id="p_abc",
        context={"environment": "production", "service": "", "sdk_version": "0.1.0", "sdk_language": "python"},
        trace=OliraTrace(object_type="conversation", object_id="conv_789"),
    )
    assert wire.trace is not None
    assert wire.trace.object_type == "conversation"


def test_action_destination_parses_with_signing_secret_on_create():
    dest = ActionDestination.model_validate(
        {
            "id": "dest_1",
            "destination_type": "webhook",
            "status": "active",
            "subscribed_event_types": ["patient.state.changed"],
            "config": {"destination_type": "webhook", "url": "https://hooks.example.com/olira"},
            "signing_secret_last4": "wxlA",
            "signing_secret": "whsec_abc123",
        }
    )
    assert dest.signing_secret == "whsec_abc123"
    assert dest.project_id is None
    assert dest.subscribed_triggers == ["patient.state.changed"]


def test_action_destination_parses_without_signing_secret_on_list():
    dest = ActionDestination.model_validate(
        {
            "id": "dest_1",
            "destination_type": "webhook",
            "status": "active",
            "subscribed_event_types": ["patient.state.changed"],
            "config": {"destination_type": "webhook", "url": "https://hooks.example.com/olira"},
            "signing_secret_last4": "wxlA",
        }
    )
    assert dest.signing_secret is None


def test_action_delivery_parses_attempts_and_payload():
    delivery = ActionDelivery.model_validate(
        {
            "id": "del_1",
            "destination_id": "dest_1",
            "destination_type": "webhook",
            "event_type": "log.no_state_change",
            "event_id": "evt_1",
            "status": "delivered",
            "attempts": [
                {
                    "attempt": 1,
                    "at": "2026-08-12T09:14:05Z",
                    "outcome": "delivered",
                    "http_status": 200,
                    "response_snippet": '{"ok":true}',
                    "duration_ms": 173,
                }
            ],
            "payload": {"id": "del_1", "type": "log.no_state_change"},
        }
    )
    assert delivery.attempts[0].http_status == 200
    assert delivery.payload == {"id": "del_1", "type": "log.no_state_change"}
    assert delivery.trigger == "log.no_state_change"


def test_action_delivery_list_result_parses_null_next_cursor():
    result = ActionDeliveryListResult.model_validate({"data": [], "next_cursor": None})
    assert result.next_cursor is None
    assert result.data == []


def test_digest_schedule_constructs_by_field_name_and_dumps_by_alias():
    """`triggers` is the customer-facing name; `event_types` is the wire alias."""
    schedule = DigestSchedule(time_of_day="09:00", triggers=["patient.state.changed"])
    assert schedule.triggers == ["patient.state.changed"]
    assert schedule.model_dump(by_alias=True, exclude_none=True) == {
        "time_of_day": "09:00",
        "timezone": "UTC",
        "event_types": ["patient.state.changed"],
    }


def test_digest_schedule_time_of_day_defaults_to_nine_am():
    """Matches the default shown in the Olira Console's create-destination flow."""
    schedule = DigestSchedule(triggers=["patient.state.changed"])
    assert schedule.time_of_day == "09:00"
    assert schedule.timezone == "UTC"


def test_recommended_digest_triggers_matches_console():
    """The Console defaults exactly this trigger to digest batching when subscribed."""
    assert RECOMMENDED_DIGEST_TRIGGERS == {ActionTrigger.PATIENT_STATE_CHANGED}


def test_action_trigger_includes_integration_sync_failed():
    assert ActionTrigger.INTEGRATION_SYNC_FAILED == "integration.sync.failed"
