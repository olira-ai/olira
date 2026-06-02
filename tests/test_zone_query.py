"""Tests for ingestion row query methods."""

from typing import Any

from olira import OliraClient, ZoneRowsResult


class _ZoneQueryTransport:
    def __init__(self) -> None:
        self.last_validated_params: dict[str, Any] | None = None
        self.last_rejected_params: dict[str, Any] | None = None

    def query_ingestion_validated_rows(self, job_id: str, params: dict[str, Any]) -> ZoneRowsResult:
        assert job_id == "job-1"
        self.last_validated_params = params
        return ZoneRowsResult(
            columns=["line", "log_type"],
            rows=[{"line": 3, "log_type": "symptom_report", "payload": {"x": 1}}],
            scanned_bytes=42,
        )

    def query_ingestion_rejected_rows(self, job_id: str, params: dict[str, Any]) -> ZoneRowsResult:
        assert job_id == "job-1"
        self.last_rejected_params = params
        return ZoneRowsResult(columns=["line", "code"], rows=[{"line": 5, "code": "missing_patient"}])

    def close(self) -> None:
        pass


def test_query_ingestion_validated_rows_passes_filters():
    transport = _ZoneQueryTransport()
    client = OliraClient(api_key="olira_test", async_flush=False)
    client._transport = transport  # type: ignore[assignment]
    client._worker = None

    result = client.query_ingestion_validated_rows(
        job_id="job-1",
        log_type="symptom_report",
        patient_id="p-1",
        limit=50,
        offset=10,
    )

    assert transport.last_validated_params == {
        "log_type": "symptom_report",
        "patient_id": "p-1",
        "limit": 50,
        "offset": 10,
    }
    assert result.scanned_bytes == 42
    assert result.rows[0]["log_type"] == "symptom_report"
    client.close()


def test_query_ingestion_rejected_rows_omits_none_params():
    transport = _ZoneQueryTransport()
    client = OliraClient(api_key="olira_test", async_flush=False)
    client._transport = transport  # type: ignore[assignment]
    client._worker = None

    client.query_ingestion_rejected_rows(job_id="job-1", code="invalid_log", limit=200)

    assert transport.last_rejected_params == {"code": "invalid_log", "limit": 200}
    client.close()


def test_get_ingestion_validated_line_requests_line_and_payload():
    transport = _ZoneQueryTransport()
    client = OliraClient(api_key="olira_test", async_flush=False)
    client._transport = transport  # type: ignore[assignment]
    client._worker = None

    row = client.get_ingestion_validated_line(job_id="job-1", line=3)

    assert transport.last_validated_params == {"line": 3, "include_payload": True, "limit": 1}
    assert row == {"line": 3, "log_type": "symptom_report", "payload": {"x": 1}}
    client.close()


def test_get_ingestion_validated_line_returns_none_when_empty():
    class EmptyTransport(_ZoneQueryTransport):
        def query_ingestion_validated_rows(self, job_id: str, params: dict[str, Any]) -> ZoneRowsResult:
            return ZoneRowsResult(columns=[], rows=[])

    client = OliraClient(api_key="olira_test", async_flush=False)
    client._transport = EmptyTransport()  # type: ignore[assignment]
    client._worker = None

    assert client.get_ingestion_validated_line(job_id="job-1", line=99) is None
    client.close()
