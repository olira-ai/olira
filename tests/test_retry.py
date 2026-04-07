"""Tests for HTTP retry policy and error mapping."""

import httpx
import pytest

from olira.exceptions import AuthError, RateLimitError
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
        transport.send_batch([{"event_name": "user_login", "patient_id": "p_1", "context": {}}])
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
        transport.send_batch([{"event_name": "user_login", "patient_id": "p_1", "context": {}}])
    assert exc_info.value.retry_after == 120
    transport.close()
