"""Tests for log() wire format and log_batch()."""

import pytest

from olira import (
    BatchError,
    BatchResult,
    LogSpec,
    OliraClient,
    OliraEnv,
    OliraLogType,
    OliraTrace,
    ValidationError,
)

# --- log() wire format tests ---


def _make_sync_client() -> tuple[OliraClient, list[dict]]:
    events_sent: list[dict] = []

    class MockTransport:
        def send_batch(self, events: list[dict]):
            events_sent.extend(events)

        def close(self):
            pass

    client = OliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    client._transport = MockTransport()  # type: ignore[assignment]
    client._worker = None
    return client, events_sent


def test_log_symptom_report_wire_format():
    client, events_sent = _make_sync_client()
    payload = {
        "instrument": "esas_r",
        "symptoms": [
            {"name": "pain", "score": 4},
            {"name": "nausea", "score": 2},
        ],
    }
    client.log(
        log_type=OliraLogType.SYMPTOM_REPORT,
        patient_id="p_abc",
        payload=payload,
    )
    assert len(events_sent) == 1
    assert events_sent[0]["log_type"] == "symptom_report"
    assert events_sent[0]["patient_id"] == "p_abc"
    props = events_sent[0]["payload"]
    assert props["instrument"] == "esas_r"
    assert len(props["symptoms"]) == 2
    client.close()


def test_log_user_login_minimal():
    client, events_sent = _make_sync_client()
    client.log(log_type=OliraLogType.USER_LOGIN, patient_id="p_123")
    assert len(events_sent) == 1
    assert events_sent[0]["log_type"] == "user_login"
    assert events_sent[0]["patient_id"] == "p_123"
    client.close()


def test_log_with_trace():
    client, events_sent = _make_sync_client()
    trace = OliraTrace(object_type="conversation", object_id="conv_789")
    client.log(
        log_type=OliraLogType.CONVERSATION_COMPLETED,
        patient_id="p_xyz",
        payload={"duration_seconds": 142},
        trace=trace,
    )
    assert events_sent[0]["trace"]["object_type"] == "conversation"
    assert events_sent[0]["trace"]["object_id"] == "conv_789"
    assert events_sent[0]["payload"]["duration_seconds"] == 142
    client.close()


def test_log_lab_results_with_performing_lab():
    client, events_sent = _make_sync_client()
    payload = {
        "results": [{"loinc_code": "718-7", "unit": "g/dL", "value_numeric": 12.0}],
        "performing_lab": {"name": "Acme Lab", "clia_number": "12D345678"},
    }
    client.log(
        log_type=OliraLogType.LAB_RESULTS_RECEIVED,
        patient_id="p_1",
        payload=payload,
    )
    assert len(events_sent) == 1
    assert events_sent[0]["payload"]["performing_lab"] == {"name": "Acme Lab", "clia_number": "12D345678"}
    client.close()


# --- log_batch() tests ---


def test_log_batch_accepted():
    batches_sent: list[list[dict]] = []

    class MockTransport:
        def send_batch(self, events: list[dict]):
            pass

        def send_batch_direct(self, events: list[dict]) -> BatchResult:
            batches_sent.append(events)
            return BatchResult(accepted=len(events), failed=0)

        def close(self):
            pass

    client = OliraClient(api_key="key", async_flush=False)
    client._transport = MockTransport()  # type: ignore[assignment]
    client._worker = None

    result = client.log_batch(
        [
            LogSpec(log_type=OliraLogType.USER_LOGIN, patient_id="p_1"),
            LogSpec(log_type=OliraLogType.LAB_RESULTS_RECEIVED, patient_id="p_2", payload={"results": []}),
            LogSpec(
                log_type=OliraLogType.SYMPTOM_REPORT,
                patient_id="p_3",
                payload={"instrument": "esas_r", "symptoms": []},
            ),
        ]
    )

    assert result.accepted == 3
    assert result.failed == 0
    assert len(result.errors) == 0
    assert len(batches_sent) == 1
    assert len(batches_sent[0]) == 3
    client.close()


def test_log_batch_partial_failure():
    class MockTransport:
        def send_batch(self, events: list[dict]):
            pass

        def send_batch_direct(self, events: list[dict]) -> BatchResult:
            return BatchResult(
                accepted=2,
                failed=1,
                errors=[BatchError(index=1, code="INVALID_PAYLOAD", message="missing required field")],
            )

        def close(self):
            pass

    client = OliraClient(api_key="key", async_flush=False)
    client._transport = MockTransport()  # type: ignore[assignment]
    client._worker = None

    result = client.log_batch(
        [
            LogSpec(log_type=OliraLogType.USER_LOGIN, patient_id="p_1"),
            LogSpec(log_type=OliraLogType.USER_LOGIN, patient_id="p_2"),
            LogSpec(log_type=OliraLogType.USER_LOGIN, patient_id="p_3"),
        ]
    )

    assert result.accepted == 2
    assert result.failed == 1
    assert len(result.errors) == 1
    assert result.errors[0].index == 1
    assert result.errors[0].code == "INVALID_PAYLOAD"
    client.close()


def test_log_batch_empty_returns_zero():
    client = OliraClient(api_key="key", async_flush=False)
    result = client.log_batch([])
    assert result.accepted == 0
    assert result.failed == 0
    client.close()


def test_log_pii_guard_raises():
    client, _ = _make_sync_client()
    with pytest.raises(ValidationError, match="email"):
        client.log(log_type=OliraLogType.USER_LOGIN, patient_id="user@example.com")
    client.close()
