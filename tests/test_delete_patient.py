"""Tests for HttpTransport.delete_patient's permanent-delete option.

Malik/Qurate needs a self-serve way to purge a duplicated patient's logs, not just
soft-delete it — this mirrors app-api's ``DELETE /v1/patients/{id}?permanent=true``.
"""

import httpx

from olira.http import HttpTransport


def _make_transport(respond):
    transport = HttpTransport(
        base_url="https://api.test.olira.ai",
        api_key="olira_test_key",
        max_retries=0,
    )
    transport._client = httpx.Client(
        base_url=transport._base_url,
        timeout=transport._timeout,
        headers=transport._client.headers,
        transport=httpx.MockTransport(respond),
    )
    return transport


def test_delete_patient_soft_delete_sends_no_permanent_param():
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    transport = _make_transport(respond)
    transport.delete_patient("p_123")
    transport.close()

    assert seen["url"].endswith("/v1/patients/p_123")
    assert "permanent" not in seen["url"]


def test_delete_patient_permanent_sets_query_param():
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True, "deleted": {"EventLog": 3}})

    transport = _make_transport(respond)
    transport.delete_patient("p_123", permanent=True)
    transport.close()

    assert "/v1/patients/p_123" in seen["url"]
    assert "permanent=true" in seen["url"]
