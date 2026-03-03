"""Tests for OliraClient and module-level init/flush/log."""

import pytest

import olira
from olira import OliraClient, OliraEnv, OliraEventType, OliraTrace


def test_init_requires_key():
    with pytest.raises(olira.OliraError, match="api_key is required"):
        olira.init()


def test_get_client_without_init_raises():
    with pytest.raises(olira.OliraError, match="init\\(\\) must be called"):
        olira.flush()


def test_client_log_builds_event():
    """With async_flush=False we send immediately; capture via mock transport."""
    events_sent: list[dict] = []

    class MockTransport:
        def send_event(self, event: dict):
            events_sent.append(event)

        def send_batch(self, events: list[dict]):
            events_sent.extend(events)

        def close(self):
            pass

    client = OliraClient(
        api_key="olira_test_key",
        environment=OliraEnv.DEVELOPMENT,
        async_flush=False,
    )
    client._transport = MockTransport()
    client._worker = None

    client.log(event_type=OliraEventType.USER_LOGIN, patient_id="p_123")
    assert len(events_sent) == 1
    assert events_sent[0]["event_name"] == "user_login"
    assert events_sent[0]["patient_id"] == "p_123"
    assert "context" in events_sent[0]
    assert events_sent[0]["context"]["environment"] == "development"
    client.close()


def test_client_log_with_trace():
    events_sent: list[dict] = []

    class MockTransport:
        def send_event(self, event: dict):
            events_sent.append(event)

        def send_batch(self, events: list[dict]):
            events_sent.extend(events)

        def close(self):
            pass

    client = OliraClient(api_key="key", async_flush=False)
    client._transport = MockTransport()
    client._worker = None

    trace = OliraTrace(object_type="conversation", object_id="conv_789")
    client.log(
        event_type=OliraEventType.CONVERSATION_COMPLETED,
        patient_id="p_abc",
        payload={"duration_seconds": 142},
        trace=trace,
    )
    assert len(events_sent) == 1
    assert events_sent[0]["event_name"] == "conversation_completed"
    assert events_sent[0]["payload"]["duration_seconds"] == 142
    assert events_sent[0]["trace"]["object_type"] == "conversation"
    assert events_sent[0]["trace"]["object_id"] == "conv_789"
    client.close()


def test_flush_noop_when_no_worker():
    client = OliraClient(
        api_key="olira_test_key",
        async_flush=False,
    )
    client.flush()
    client.close()
