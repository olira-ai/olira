"""Tests for get_events() and delete_events() on OliraClient and AsyncOliraClient."""

import pytest

import olira
from olira import (
    AsyncOliraClient,
    DeleteResult,
    EventQueryResult,
    EventRecord,
    OliraClient,
    OliraEventType,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_client() -> tuple[OliraClient, list]:
    calls: list = []

    class MockTransport:
        def send_event(self, event: dict):
            pass

        def send_batch(self, events: list[dict]):
            pass

        def close(self):
            pass

        def get_events(self, params: dict) -> EventQueryResult:
            calls.append(("get_events", params))
            return EventQueryResult(events=[], total=0, has_more=False)

        def delete_events(self, body: dict) -> DeleteResult:
            calls.append(("delete_events", body))
            return DeleteResult(deleted_count=3, patient_id=body["patient_id"])

    client = OliraClient(api_key="olira_test_key", async_flush=False)
    client._transport = MockTransport()  # type: ignore[assignment]
    client._worker = None
    return client, calls


# ---------------------------------------------------------------------------
# Sync client — get_events
# ---------------------------------------------------------------------------


def test_get_events_sends_correct_params():
    client, calls = _make_sync_client()
    result = client.get_events(
        patient_id="p_abc",
        event_type=OliraEventType.MEDICATION_DOSE_UPDATE,
        from_timestamp="2026-01-01T00:00:00Z",
        to_timestamp="2026-01-31T23:59:59Z",
    )
    assert len(calls) == 1
    method, params = calls[0]
    assert method == "get_events"
    assert params["patient_id"] == "p_abc"
    assert params["event_type"] == "medication_dose_update"
    assert params["from_timestamp"] == "2026-01-01T00:00:00Z"
    assert params["to_timestamp"] == "2026-01-31T23:59:59Z"
    assert params["limit"] == 100
    assert params["offset"] == 0
    assert isinstance(result, EventQueryResult)
    client.close()


def test_get_events_ingested_time_filter():
    client, calls = _make_sync_client()
    client.get_events(
        patient_id="p_abc",
        ingested_after="2026-01-14T09:55:00Z",
        ingested_before="2026-01-14T10:05:00Z",
    )
    _, params = calls[0]
    assert params["ingested_after"] == "2026-01-14T09:55:00Z"
    assert params["ingested_before"] == "2026-01-14T10:05:00Z"
    assert "event_type" not in params
    client.close()


def test_get_events_omits_none_params():
    client, calls = _make_sync_client()
    client.get_events(patient_id="p_abc")
    _, params = calls[0]
    assert "event_type" not in params
    assert "from_timestamp" not in params
    assert "to_timestamp" not in params
    assert "ingested_after" not in params
    assert "ingested_before" not in params
    client.close()


def test_get_events_custom_limit_offset():
    client, calls = _make_sync_client()
    client.get_events(patient_id="p_abc", limit=10, offset=50)
    _, params = calls[0]
    assert params["limit"] == 10
    assert params["offset"] == 50
    client.close()


# ---------------------------------------------------------------------------
# Sync client — delete_events
# ---------------------------------------------------------------------------


def test_delete_events_by_type_and_timestamp():
    client, calls = _make_sync_client()
    result = client.delete_events(
        patient_id="p_abc",
        event_type=OliraEventType.MEDICATION_DOSE_UPDATE,
        from_timestamp="2026-01-01T00:00:00Z",
        to_timestamp="2026-01-31T23:59:59Z",
    )
    assert len(calls) == 1
    method, body = calls[0]
    assert method == "delete_events"
    assert body["patient_id"] == "p_abc"
    assert body["event_type"] == "medication_dose_update"
    assert body["from_timestamp"] == "2026-01-01T00:00:00Z"
    assert body["to_timestamp"] == "2026-01-31T23:59:59Z"
    assert isinstance(result, DeleteResult)
    assert result.deleted_count == 3
    assert result.patient_id == "p_abc"
    client.close()


def test_delete_events_by_ingestion_window():
    client, calls = _make_sync_client()
    client.delete_events(
        patient_id="p_abc",
        ingested_after="2026-01-14T09:55:00Z",
        ingested_before="2026-01-14T10:05:00Z",
    )
    _, body = calls[0]
    assert body["ingested_after"] == "2026-01-14T09:55:00Z"
    assert body["ingested_before"] == "2026-01-14T10:05:00Z"
    assert "event_type" not in body
    client.close()


def test_delete_events_by_event_ids():
    client, calls = _make_sync_client()
    ids = ["e1a2b3c4-1111-0000-0000-000000000000", "e1a2b3c4-2222-0000-0000-000000000000"]
    client.delete_events(patient_id="p_abc", event_ids=ids)
    _, body = calls[0]
    assert body["event_ids"] == ids
    client.close()


def test_delete_events_no_filter_raises():
    client, _ = _make_sync_client()
    with pytest.raises(ValidationError, match="at least one filter"):
        client.delete_events(patient_id="p_abc")
    client.close()


def test_delete_events_no_filter_raises_module_level():
    """Module-level delete_events() with no filter also raises before any network call."""
    olira.init(api_key="olira_test_key", async_flush=False)
    client = olira._get_client()
    client._worker = None

    calls: list = []

    class MockTransport:
        def delete_events(self, body: dict) -> DeleteResult:
            calls.append(body)
            return DeleteResult(deleted_count=0, patient_id=body["patient_id"])

        def close(self):
            pass

    client._transport = MockTransport()  # type: ignore[assignment]

    with pytest.raises(ValidationError, match="at least one filter"):
        olira.delete_events(patient_id="p_abc")

    assert len(calls) == 0


# ---------------------------------------------------------------------------
# Module-level proxies
# ---------------------------------------------------------------------------


def test_module_level_get_events():
    olira.init(api_key="olira_test_key", async_flush=False)
    client = olira._get_client()
    client._worker = None
    calls: list = []

    class MockTransport:
        def get_events(self, params: dict) -> EventQueryResult:
            calls.append(params)
            return EventQueryResult(
                events=[
                    EventRecord(
                        event_id="e1a2b3c4-0000-0000-0000-000000000001",
                        event_type=OliraEventType.USER_LOGIN,
                        patient_id="p_abc",
                        timestamp="2026-01-15T10:00:00Z",
                        ingested_at="2026-01-15T10:00:01Z",
                        payload={},
                    )
                ],
                total=1,
                has_more=False,
            )

        def close(self):
            pass

    client._transport = MockTransport()  # type: ignore[assignment]

    result = olira.get_events(patient_id="p_abc", event_type=OliraEventType.USER_LOGIN)

    assert len(calls) == 1
    assert calls[0]["patient_id"] == "p_abc"
    assert result.total == 1
    assert result.events[0].event_type == OliraEventType.USER_LOGIN
    assert result.events[0].patient_id == "p_abc"


# ---------------------------------------------------------------------------
# Async client — get_events and delete_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_get_events():
    calls: list = []

    class MockTransport:
        async def send_batch(self, events):
            pass

        async def get_events(self, params: dict) -> EventQueryResult:
            calls.append(("get_events", params))
            return EventQueryResult(events=[], total=0, has_more=False)

        async def delete_events(self, body: dict) -> DeleteResult:
            calls.append(("delete_events", body))
            return DeleteResult(deleted_count=2, patient_id=body["patient_id"])

        async def aclose(self):
            pass

    async with AsyncOliraClient(api_key="key") as client:
        client._transport = MockTransport()  # type: ignore[assignment]

        result = await client.get_events(
            patient_id="p_async",
            event_type=OliraEventType.SYMPTOM_REPORT,
            from_timestamp="2026-01-01T00:00:00Z",
        )

    assert len(calls) == 1
    method, params = calls[0]
    assert method == "get_events"
    assert params["patient_id"] == "p_async"
    assert params["event_type"] == "symptom_report"
    assert isinstance(result, EventQueryResult)


@pytest.mark.asyncio
async def test_async_delete_events():
    calls: list = []

    class MockTransport:
        async def send_batch(self, events):
            pass

        async def delete_events(self, body: dict) -> DeleteResult:
            calls.append(body)
            return DeleteResult(deleted_count=5, patient_id=body["patient_id"])

        async def aclose(self):
            pass

    async with AsyncOliraClient(api_key="key") as client:
        client._transport = MockTransport()  # type: ignore[assignment]

        result = await client.delete_events(
            patient_id="p_async",
            ingested_after="2026-01-14T09:00:00Z",
            ingested_before="2026-01-14T11:00:00Z",
        )

    assert len(calls) == 1
    assert calls[0]["patient_id"] == "p_async"
    assert result.deleted_count == 5


@pytest.mark.asyncio
async def test_async_delete_events_no_filter_raises():
    class MockTransport:
        async def send_batch(self, events):
            pass

        async def aclose(self):
            pass

    async with AsyncOliraClient(api_key="key") as client:
        client._transport = MockTransport()  # type: ignore[assignment]

        with pytest.raises(ValidationError, match="at least one filter"):
            await client.delete_events(patient_id="p_async")


@pytest.mark.asyncio
async def test_async_get_events_requires_context_manager():
    client = AsyncOliraClient(api_key="key")
    with pytest.raises(ValidationError, match="async context manager"):
        await client.get_events(patient_id="p_abc", event_type=OliraEventType.USER_LOGIN)


@pytest.mark.asyncio
async def test_async_delete_events_requires_context_manager():
    client = AsyncOliraClient(api_key="key")
    with pytest.raises(ValidationError, match="async context manager"):
        await client.delete_events(patient_id="p_abc", event_type=OliraEventType.USER_LOGIN)
