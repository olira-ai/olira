"""Tests for OliraClient/AsyncOliraClient.log_fhir — idempotency_key forwarding (OLI-2158)."""

import pytest

from olira import AsyncOliraClient, BatchResult, OliraClient, OliraEnv


def test_log_fhir_forwards_idempotency_key():
    calls: list[dict] = []

    class MockTransport:
        def log_fhir(self, patient_id, resource, idempotency_key=None):
            calls.append({"patient_id": patient_id, "resource": resource, "idempotency_key": idempotency_key})
            return BatchResult(accepted=1, failed=0)

        def close(self):
            pass

    client = OliraClient(api_key="olira_test_key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    client._transport = MockTransport()
    client._worker = None

    client.log_fhir(
        patient_id="p_1",
        resource={"resourceType": "Patient", "id": "abc"},
        idempotency_key="retry-key-1",
    )

    assert len(calls) == 1
    assert calls[0]["idempotency_key"] == "retry-key-1"
    client.close()


def test_log_fhir_omits_idempotency_key_when_none():
    calls: list[dict] = []

    class MockTransport:
        def log_fhir(self, patient_id, resource, idempotency_key=None):
            calls.append(idempotency_key)
            return BatchResult(accepted=1, failed=0)

        def close(self):
            pass

    client = OliraClient(api_key="olira_test_key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    client._transport = MockTransport()
    client._worker = None

    client.log_fhir(patient_id="p_1", resource={"resourceType": "Patient", "id": "abc"})

    assert calls == [None]
    client.close()


@pytest.mark.asyncio
async def test_async_log_fhir_forwards_idempotency_key():
    calls: list[dict] = []

    class MockTransport:
        async def log_fhir(self, patient_id, resource, idempotency_key=None):
            calls.append({"patient_id": patient_id, "resource": resource, "idempotency_key": idempotency_key})
            return BatchResult(accepted=1, failed=0)

        async def aclose(self):
            pass

    async with AsyncOliraClient(api_key="olira_test_key", environment=OliraEnv.DEVELOPMENT) as client:
        client._transport = MockTransport()
        await client.log_fhir(
            patient_id="p_async_1",
            resource={"resourceType": "Patient", "id": "def"},
            idempotency_key="retry-key-2",
        )

    assert len(calls) == 1
    assert calls[0]["idempotency_key"] == "retry-key-2"


def test_log_fhir_request_body_includes_idempotency_key_only_when_set():
    """HttpTransport.log_fhir must send idempotency_key in the JSON body only when non-None."""
    from olira.http import HttpTransport

    captured: list[dict] = []

    class FakeHttpTransport(HttpTransport):
        def _request(self, method, path, json=None, params=None, retryable=True):  # noqa: ARG002
            captured.append(json or {})
            return {"accepted": 1, "failed": 0, "errors": []}

    transport = FakeHttpTransport.__new__(FakeHttpTransport)
    transport.log_fhir(patient_id="p_1", resource={"resourceType": "Patient", "id": "abc"})
    transport.log_fhir(
        patient_id="p_1",
        resource={"resourceType": "Patient", "id": "abc"},
        idempotency_key="retry-key-3",
    )

    assert "idempotency_key" not in captured[0]
    assert captured[1]["idempotency_key"] == "retry-key-3"
