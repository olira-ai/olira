"""Tests for AsyncOliraClient."""

import pytest

from olira import AsyncOliraClient, BatchResult, LogSpec, OliraEnv, OliraLogType, OliraTrace


@pytest.mark.asyncio
async def test_async_client_context_manager():
    events_sent: list[dict] = []

    class MockTransport:
        async def send_batch(self, events: list[dict]):
            events_sent.extend(events)

        async def aclose(self):
            pass

    transport = MockTransport()

    async with AsyncOliraClient(
        api_key="olira_test_key",
        environment=OliraEnv.DEVELOPMENT,
    ) as client:
        client._transport = transport
        await client.log(log_type=OliraLogType.USER_LOGIN, patient_id="p_async_123")
        await client.flush()

    assert len(events_sent) == 1
    assert events_sent[0]["log_type"] == "user_login"
    assert events_sent[0]["patient_id"] == "p_async_123"
    assert events_sent[0]["context"]["environment"] == "development"


@pytest.mark.asyncio
async def test_async_client_log_with_payload():
    events_sent: list[dict] = []

    class MockTransport:
        async def send_batch(self, events: list[dict]):
            events_sent.extend(events)

        async def aclose(self):
            pass

    from olira import EsasItem

    transport = MockTransport()
    async with AsyncOliraClient(api_key="key", batch_size=10) as client:
        client._transport = transport
        payload = {
            "instrument": "esas_r",
            "symptoms": [
                EsasItem(name="pain", score=3).model_dump(),
                EsasItem(name="tiredness", score=2).model_dump(),
            ],
        }
        await client.log(
            log_type=OliraLogType.SYMPTOM_REPORT,
            patient_id="subj_1",
            payload=payload,
        )
        await client.flush()

    assert len(events_sent) == 1
    assert events_sent[0]["log_type"] == "symptom_report"
    assert events_sent[0]["payload"]["instrument"] == "esas_r"
    assert len(events_sent[0]["payload"]["symptoms"]) == 2


@pytest.mark.asyncio
async def test_async_client_log_batch():
    batches_sent: list[list[dict]] = []

    class MockTransport:
        async def send_batch(self, events: list[dict]):
            pass

        async def send_batch_direct(self, events: list[dict]) -> BatchResult:
            batches_sent.append(events)
            return BatchResult(accepted=len(events), failed=0)

        async def aclose(self):
            pass

    async with AsyncOliraClient(api_key="key") as client:
        client._transport = MockTransport()
        result = await client.log_batch(
            [
                LogSpec(log_type=OliraLogType.USER_LOGIN, patient_id="p_1"),
                LogSpec(
                    log_type=OliraLogType.SYMPTOM_REPORT,
                    patient_id="p_2",
                    payload={"instrument": "esas_r", "symptoms": []},
                ),
            ]
        )

    assert result.accepted == 2
    assert result.failed == 0
    assert len(batches_sent) == 1
    assert len(batches_sent[0]) == 2
    assert batches_sent[0][0]["log_type"] == "user_login"
    assert batches_sent[0][1]["log_type"] == "symptom_report"


@pytest.mark.asyncio
async def test_async_log_with_trace():
    events_sent: list[dict] = []

    class MockTransport:
        async def send_batch(self, events: list[dict]):
            events_sent.extend(events)

        async def aclose(self):
            pass

    async with AsyncOliraClient(api_key="key") as client:
        client._transport = MockTransport()
        trace = OliraTrace(object_type="conversation", object_id="conv_42")
        await client.log(
            log_type=OliraLogType.CONVERSATION_COMPLETED,
            patient_id="p_xyz",
            payload={"duration_seconds": 60},
            trace=trace,
        )
        await client.flush()

    assert len(events_sent) == 1
    assert events_sent[0]["trace"]["object_type"] == "conversation"
    assert events_sent[0]["trace"]["object_id"] == "conv_42"
