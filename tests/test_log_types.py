"""Tests for the log-type catalog methods on OliraClient/AsyncOliraClient.

Follows the hand-rolled MockTransport convention used elsewhere in this suite
(test_schema_management.py): swap a fake transport into the client and assert
on both the request shape it receives and the response it hands back.
"""

import pytest

from olira import AsyncOliraClient, LogType, OliraClient, OliraEnv


def _make_log_type(subtype: str = "symptom_report") -> LogType:
    return LogType(
        subtype=subtype,
        category="symptom_reports",
        display_name="Symptom report",
        description="Reserved for structured symptom severity with a defined instrument.",
        payload_schema={"type": "object", "required": ["instrument", "symptoms"]},
        payload_description="instrument (required), symptoms[]",
        sources=["logged"],
        version=1,
    )


class _MockTransport:
    def __init__(self):
        self.calls: list[tuple] = []

    def close(self):
        pass

    def list_log_types(self):
        self.calls.append(("list_log_types",))
        return [_make_log_type("mood_report"), _make_log_type("symptom_report")]

    def get_log_type(self, subtype):
        self.calls.append(("get_log_type", subtype))
        return _make_log_type(subtype)


def _client_with_mock() -> tuple[OliraClient, _MockTransport]:
    client = OliraClient(api_key="olira_test_key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    original_transport = client._transport
    transport = _MockTransport()
    client._transport = transport
    client._worker = None
    original_transport.close()
    return client, transport


def test_list_log_types_returns_full_catalog_entries():
    client, transport = _client_with_mock()
    result = client.list_log_types()
    assert [t.subtype for t in result] == ["mood_report", "symptom_report"]
    assert result[1].payload_schema == {"type": "object", "required": ["instrument", "symptoms"]}
    assert transport.calls == [("list_log_types",)]
    client.close()


def test_get_log_type_passes_subtype_through():
    client, transport = _client_with_mock()
    result = client.get_log_type(subtype="mood_report")
    assert result.subtype == "mood_report"
    assert transport.calls == [("get_log_type", "mood_report")]
    client.close()


class _AsyncMockTransport:
    def __init__(self):
        self.calls: list[tuple] = []

    async def aclose(self):
        pass

    async def list_log_types(self):
        self.calls.append(("list_log_types",))
        return [_make_log_type("mood_report"), _make_log_type("symptom_report")]

    async def get_log_type(self, subtype):
        self.calls.append(("get_log_type", subtype))
        return _make_log_type(subtype)


@pytest.mark.asyncio
async def test_async_client_list_and_get_log_type():
    transport = _AsyncMockTransport()
    async with AsyncOliraClient(api_key="olira_test_key", environment=OliraEnv.DEVELOPMENT) as client:
        original_transport = client._transport
        client._transport = transport
        await original_transport.aclose()
        result = await client.list_log_types()
        assert [t.subtype for t in result] == ["mood_report", "symptom_report"]

        one = await client.get_log_type(subtype="symptom_report")
        assert one.subtype == "symptom_report"

    assert transport.calls == [("list_log_types",), ("get_log_type", "symptom_report")]
