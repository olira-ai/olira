"""HTTP transport for the ingestion API with retry policy and key redaction."""

import asyncio
import logging
import time
from typing import Any

import httpx

from .exceptions import AuthError, NetworkError, RateLimitError, ServerError, ValidationError
from .models import (
    BatchResult,
    Patient,
    PatientBatchResult,
    PatientListResult,
    PatientToken,
)

logger = logging.getLogger("olira")

# Redact API key in all log output (SPEC: key never logged)
REDACTED_KEY = "olira_***"


def _redact_key(api_key: str | None) -> str:
    if not api_key:
        return REDACTED_KEY
    return REDACTED_KEY


def _should_retry(status_code: int) -> bool:
    """True if we should retry: 408, 429, 5xx."""
    if status_code in (408, 429):
        return True
    if 500 <= status_code < 600:
        return True
    return False


def _parse_retry_after(response: httpx.Response) -> int:
    """Parse Retry-After header; return seconds (default 60)."""
    value = response.headers.get("Retry-After", "60")
    try:
        return int(value)
    except ValueError:
        return 60


def _parse_batch_result(body: dict[str, Any]) -> BatchResult:
    """Parse /v1/logs/batch response body into BatchResult."""
    return BatchResult.model_validate(body)


def _parse_patient(body: dict[str, Any]) -> Patient:
    """Parse a single patient response body into a Patient model."""
    return Patient.model_validate(body)


def _parse_patient_list_result(body: dict[str, Any]) -> PatientListResult:
    """Parse GET /v1/patients response into PatientListResult."""
    return PatientListResult.model_validate(body)


def _parse_patient_token(body: dict[str, Any]) -> PatientToken:
    """Parse POST /v1/auth/token response into PatientToken."""
    return PatientToken.model_validate(body)


class HttpTransport:
    """Sync HTTP transport: POST /v1/logs/batch with retry."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpTransport":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def send_batch(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Send a batch of logs (background worker path). Returns raw response dict."""
        return self._request("POST", "/v1/logs/batch", json={"events": events})  # type: ignore[no-any-return]

    def send_batch_direct(self, events: list[dict[str, Any]]) -> BatchResult:
        """Send a batch directly (log_batch() path). Returns parsed BatchResult."""
        raw = self._request("POST", "/v1/logs/batch", json={"events": events})
        return _parse_batch_result(raw)

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_exception: Exception | None = None
        retry_after_seconds: int = 0

        for attempt in range(self._max_retries + 1):
            if retry_after_seconds > 0:
                time.sleep(retry_after_seconds)
            retry_after_seconds = 0

            try:
                response = self._client.request(method, path, json=json, params=params)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
                last_exception = NetworkError(str(e))
                if attempt < self._max_retries:
                    delay = min(2**attempt + (time.time() % 1), 60)
                    logger.debug(
                        "Request failed (attempt %s/%s), retry in %.1fs: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                        _redact_key(self._api_key),
                    )
                    time.sleep(delay)
                continue

            status = response.status_code

            # Auth: never retry
            if status in (401, 403):
                raise AuthError(f"API key rejected (HTTP {status}). Check key validity and scope.")

            # Conflict: server-side constraint violation (e.g. duplicate external identifier)
            if status == 409:
                response.read()
                raise ServerError(
                    f"Request rejected (HTTP {status}): {response.text[:500]}",
                    status_code=status,
                )

            # Permanent client errors: don't retry
            if status in (400, 404, 422):
                response.read()
                raise ValidationError(f"Request rejected (HTTP {status}): {response.text[:500]}")

            # Rate limit: retry after Retry-After
            if status == 429:
                retry_after_seconds = _parse_retry_after(response)
                if attempt == self._max_retries:
                    raise RateLimitError(
                        "Rate limited; retry after backoff",
                        retry_after=retry_after_seconds,
                    )
                logger.debug(
                    "Rate limited, retry after %ss (%s)",
                    retry_after_seconds,
                    _redact_key(self._api_key),
                )
                continue

            # Transient: retry with backoff
            if _should_retry(status):
                if attempt == self._max_retries:
                    raise ServerError(f"Server error (HTTP {status}) after retries")
                delay = min(2**attempt + (time.time() % 1), 60)
                logger.debug(
                    "Server error %s (attempt %s/%s), retry in %.1fs",
                    status,
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                )
                time.sleep(delay)
                continue

            # Success
            if 200 <= status < 300:
                return response.json() if response.content else {}

            response.read()
            last_exception = ServerError(f"Unexpected HTTP {status}")
            break

        if last_exception:
            raise last_exception
        return {}

    def create_patient(self, body: dict[str, Any]) -> Patient:
        """Create a patient (POST /v1/patients). Requires api:manage-patients scope."""
        raw = self._request("POST", "/v1/patients", json=body)
        return _parse_patient(raw)

    def get_patient(self, patient_id: str) -> Patient:
        """Get a patient by id (GET /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        raw = self._request("GET", f"/v1/patients/{patient_id}")
        return _parse_patient(raw)

    def list_patients(self, params: dict[str, Any]) -> PatientListResult:
        """List patients (GET /v1/patients). Requires api:manage-patients scope."""
        raw = self._request("GET", "/v1/patients", params=params)
        return _parse_patient_list_result(raw)

    def update_patient(self, patient_id: str, body: dict[str, Any]) -> Patient:
        """Update a patient (PUT /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        raw = self._request("PUT", f"/v1/patients/{patient_id}", json=body)
        return _parse_patient(raw)

    def delete_patient(self, patient_id: str) -> None:
        """Soft-delete a patient (DELETE /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        self._request("DELETE", f"/v1/patients/{patient_id}")

    def create_patients_batch(self, patients: list[dict[str, Any]]) -> PatientBatchResult:
        """Batch-create patients (POST /v1/patients/batch). Requires api:manage-patients scope."""
        raw = self._request("POST", "/v1/patients/batch", json={"patients": patients})
        return PatientBatchResult.model_validate(raw)

    def get_patient_token(self, body: dict[str, Any]) -> PatientToken:
        """Mint a patient-scoped JWT (POST /v1/auth/token). Requires sdk:patient-token scope."""
        raw = self._request("POST", "/v1/auth/token", json=body)
        return _parse_patient_token(raw)


class AsyncHttpTransport:
    """Async HTTP transport: POST /v1/logs/batch with retry."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_batch(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Send a batch of logs (background worker path). Returns raw response dict."""
        return await self._request("POST", "/v1/logs/batch", json={"events": events})  # type: ignore[no-any-return]

    async def send_batch_direct(self, events: list[dict[str, Any]]) -> BatchResult:
        """Send a batch directly (log_batch() path). Returns parsed BatchResult."""
        raw = await self._request("POST", "/v1/logs/batch", json={"events": events})
        return _parse_batch_result(raw)

    async def create_patient(self, body: dict[str, Any]) -> Patient:
        """Create a patient (POST /v1/patients). Requires api:manage-patients scope."""
        raw = await self._request("POST", "/v1/patients", json=body)
        return _parse_patient(raw)

    async def get_patient(self, patient_id: str) -> Patient:
        """Get a patient by id (GET /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        raw = await self._request("GET", f"/v1/patients/{patient_id}")
        return _parse_patient(raw)

    async def list_patients(self, params: dict[str, Any]) -> PatientListResult:
        """List patients (GET /v1/patients). Requires api:manage-patients scope."""
        raw = await self._request("GET", "/v1/patients", params=params)
        return _parse_patient_list_result(raw)

    async def update_patient(self, patient_id: str, body: dict[str, Any]) -> Patient:
        """Update a patient (PUT /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        raw = await self._request("PUT", f"/v1/patients/{patient_id}", json=body)
        return _parse_patient(raw)

    async def delete_patient(self, patient_id: str) -> None:
        """Soft-delete a patient (DELETE /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        await self._request("DELETE", f"/v1/patients/{patient_id}")

    async def create_patients_batch(self, patients: list[dict[str, Any]]) -> PatientBatchResult:
        """Batch-create patients (POST /v1/patients/batch). Requires api:manage-patients scope."""
        raw = await self._request("POST", "/v1/patients/batch", json={"patients": patients})
        return PatientBatchResult.model_validate(raw)

    async def get_patient_token(self, body: dict[str, Any]) -> PatientToken:
        """Mint a patient-scoped JWT (POST /v1/auth/token). Requires sdk:patient-token scope."""
        raw = await self._request("POST", "/v1/auth/token", json=body)
        return _parse_patient_token(raw)

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_exception: Exception | None = None
        retry_after_seconds: int = 0

        for attempt in range(self._max_retries + 1):
            if retry_after_seconds > 0:
                await asyncio.sleep(retry_after_seconds)
            retry_after_seconds = 0

            try:
                response = await self._client.request(method, path, json=json, params=params)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
                last_exception = NetworkError(str(e))
                if attempt < self._max_retries:
                    delay = min(2**attempt + (time.time() % 1), 60)
                    logger.debug(
                        "Request failed (attempt %s/%s), retry in %.1fs: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                        _redact_key(self._api_key),
                    )
                    await asyncio.sleep(delay)
                continue

            status = response.status_code

            if status in (401, 403):
                raise AuthError(f"API key rejected (HTTP {status}). Check key validity and scope.")

            if status == 409:
                await response.aread()
                raise ServerError(
                    f"Request rejected (HTTP {status}): {response.text[:500]}",
                    status_code=status,
                )

            if status in (400, 404, 422):
                await response.aread()
                raise ValidationError(f"Request rejected (HTTP {status}): {response.text[:500]}")

            if status == 429:
                retry_after_seconds = _parse_retry_after(response)
                if attempt == self._max_retries:
                    raise RateLimitError(
                        "Rate limited; retry after backoff",
                        retry_after=retry_after_seconds,
                    )
                logger.debug(
                    "Rate limited, retry after %ss (%s)",
                    retry_after_seconds,
                    _redact_key(self._api_key),
                )
                continue

            if _should_retry(status):
                if attempt == self._max_retries:
                    raise ServerError(f"Server error (HTTP {status}) after retries")
                delay = min(2**attempt + (time.time() % 1), 60)
                await asyncio.sleep(delay)
                continue

            if 200 <= status < 300:
                return response.json() if response.content else {}

            await response.aread()
            last_exception = ServerError(f"Unexpected HTTP {status}")
            break

        if last_exception:
            raise last_exception
        return {}
