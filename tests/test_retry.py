"""Tests for HTTP retry policy and error mapping."""

import httpx
import pytest

from olira.exceptions import AuthError, RateLimitError, ServerError
from olira.http import HttpTransport


def test_401_raises_auth_error():
    """401 should raise AuthError immediately, no retry."""

    def respond_401(request):
        return httpx.Response(401, text="Unauthorized")

    transport = HttpTransport(
        base_url="https://api.test.olira.ai",
        api_key="olira_test_key",
        max_retries=2,
    )
    transport._client = httpx.Client(
        base_url=transport._base_url,
        timeout=transport._timeout,
        headers=transport._client.headers,
        transport=httpx.MockTransport(respond_401),
    )
    with pytest.raises(AuthError, match="401"):
        transport.send_batch([{"log_type": "user_login", "patient_id": "p_1", "context": {}}])
    transport.close()


def test_429_parses_retry_after():
    """429 with Retry-After header should be reflected in RateLimitError."""

    def respond_429(request):
        return httpx.Response(429, headers={"Retry-After": "120"}, text="Too Many Requests")

    transport = HttpTransport(
        base_url="https://api.test.olira.ai",
        api_key="olira_test_key",
        max_retries=0,
    )
    transport._client = httpx.Client(
        base_url=transport._base_url,
        timeout=transport._timeout,
        headers=transport._client.headers,
        transport=httpx.MockTransport(respond_429),
    )
    with pytest.raises(RateLimitError) as exc_info:
        transport.send_batch([{"log_type": "user_login", "patient_id": "p_1", "context": {}}])
    assert exc_info.value.retry_after == 120
    transport.close()


def test_create_project_does_not_retry_on_500():
    """Non-idempotent project creation must not be replayed on retryable errors."""
    calls = {"count": 0}

    def respond_500(request):
        calls["count"] += 1
        return httpx.Response(500, text="Internal Server Error")

    transport = HttpTransport(
        base_url="https://api.test.olira.ai",
        api_key="olira_test_key",
        max_retries=3,
    )
    transport._client = httpx.Client(
        base_url=transport._base_url,
        timeout=transport._timeout,
        headers=transport._client.headers,
        transport=httpx.MockTransport(respond_500),
    )
    with pytest.raises(ServerError):
        transport.create_project({"name": "Dev Sandbox"})
    assert calls["count"] == 1
    transport.close()


def test_log_fhir_without_idempotency_key_does_not_retry_on_500():
    """No key means no stable dedup anchor server-side — a lost response could otherwise
    be replayed by the transport itself and duplicate the event."""
    calls = {"count": 0}

    def respond_500(request):
        calls["count"] += 1
        return httpx.Response(500, text="Internal Server Error")

    transport = HttpTransport(
        base_url="https://api.test.olira.ai",
        api_key="olira_test_key",
        max_retries=3,
    )
    transport._client = httpx.Client(
        base_url=transport._base_url,
        timeout=transport._timeout,
        headers=transport._client.headers,
        transport=httpx.MockTransport(respond_500),
    )
    with pytest.raises(ServerError):
        transport.log_fhir("p_1", {"resourceType": "Patient", "id": "abc"})
    assert calls["count"] == 1
    transport.close()


def test_log_fhir_with_idempotency_key_retries_on_500():
    """A caller-supplied key makes the server-side dedup anchor stable, so the transport's
    own retry is safe — must retry the way any other idempotent call does."""
    calls = {"count": 0}

    def respond_500_then_ok(request):
        calls["count"] += 1
        if calls["count"] < 2:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, json={"accepted": 1, "failed": 0, "errors": []})

    transport = HttpTransport(
        base_url="https://api.test.olira.ai",
        api_key="olira_test_key",
        max_retries=3,
    )
    transport._client = httpx.Client(
        base_url=transport._base_url,
        timeout=transport._timeout,
        headers=transport._client.headers,
        transport=httpx.MockTransport(respond_500_then_ok),
    )
    result = transport.log_fhir("p_1", {"resourceType": "Patient", "id": "abc"}, idempotency_key="retry-key-1")
    assert result.accepted == 1
    assert calls["count"] == 2
    transport.close()
