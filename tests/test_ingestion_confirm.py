"""Tests for retry-safe ingestion job confirm helpers."""

import pytest

from olira.client import OliraClient
from olira.exceptions import ServerError
from olira.ingestion_confirm import (
    confirm_ingestion_job_resilient,
    ensure_skip_backfill_before_confirm,
    is_409_past_review_gate,
)
from olira.models import IngestionJob, IngestionJobStatus


def _job(status: str, *, skip_backfill: bool = False) -> IngestionJob:
    return IngestionJob(
        job_id="job_1",
        status=IngestionJobStatus(status),
        stage=status,
        skip_backfill=skip_backfill,
    )


def test_is_409_past_review_gate():
    assert is_409_past_review_gate("replaying")
    assert is_409_past_review_gate("cancelled")
    assert is_409_past_review_gate("failed")
    assert is_409_past_review_gate("completed_with_errors")
    assert not is_409_past_review_gate("awaiting_confirmation")
    assert not is_409_past_review_gate("validating")
    assert not is_409_past_review_gate("inserting_logs")


def test_ensure_skip_backfill_tolerates_patch_409_when_already_replaying():
    calls = {"patch": 0, "get": 0}

    def patch() -> IngestionJob:
        calls["patch"] += 1
        raise ServerError("conflict", status_code=409)

    def get_job() -> IngestionJob:
        calls["get"] += 1
        return _job("replaying", skip_backfill=True)

    ensure_skip_backfill_before_confirm(patch_skip_backfill=patch, get_job=get_job)
    assert calls == {"patch": 1, "get": 1}


@pytest.mark.parametrize("status", ["cancelled", "failed", "completed"])
def test_ensure_skip_backfill_tolerates_patch_409_for_terminal_after_review(status: str):
    def patch() -> IngestionJob:
        raise ServerError("conflict", status_code=409)

    def get_job() -> IngestionJob:
        return _job(status)

    ensure_skip_backfill_before_confirm(patch_skip_backfill=patch, get_job=get_job)


def test_ensure_skip_backfill_reraises_patch_409_when_still_in_phase1():
    def patch() -> IngestionJob:
        raise ServerError("conflict", status_code=409)

    def get_job() -> IngestionJob:
        return _job("validating")

    with pytest.raises(ServerError):
        ensure_skip_backfill_before_confirm(patch_skip_backfill=patch, get_job=get_job)


def test_confirm_resilient_retry_after_confirm_succeeded():
    """PATCH 409 + confirm 409 both return current job when already replaying."""
    calls = {"patch": 0, "confirm": 0, "get": 0}

    def patch() -> IngestionJob:
        calls["patch"] += 1
        raise ServerError("patch conflict", status_code=409)

    def get_job() -> IngestionJob:
        calls["get"] += 1
        return _job("replaying", skip_backfill=True)

    def confirm() -> IngestionJob:
        calls["confirm"] += 1
        raise ServerError("confirm conflict", status_code=409)

    result = confirm_ingestion_job_resilient(
        skip_backfill=True,
        patch_skip_backfill=patch,
        get_job=get_job,
        confirm=confirm,
    )
    assert result.status == IngestionJobStatus.REPLAYING
    assert calls["patch"] == 1
    assert calls["confirm"] == 1
    assert calls["get"] == 2


def test_confirm_resilient_returns_job_when_confirm_409_and_cancelled():
    def confirm() -> IngestionJob:
        raise ServerError("confirm conflict", status_code=409)

    def get_job() -> IngestionJob:
        return _job("cancelled")

    result = confirm_ingestion_job_resilient(
        skip_backfill=False,
        patch_skip_backfill=lambda: _job("cancelled"),
        get_job=get_job,
        confirm=confirm,
    )
    assert result.status == IngestionJobStatus.CANCELLED


def test_confirm_ingestion_job_client_integration():
    """Simulate retry: PATCH 409 + confirm 409 while job is already replaying."""

    class MockTransport:
        def __init__(self) -> None:
            self.patch_calls = 0
            self.confirm_calls = 0
            # Server already confirmed on a prior attempt; client is retrying.
            self.status = "replaying"

        def patch_ingestion_job(self, job_id: str, body: dict) -> IngestionJob:
            self.patch_calls += 1
            raise ServerError("patch conflict", status_code=409)

        def get_ingestion_job(self, job_id: str) -> IngestionJob:
            return _job(self.status, skip_backfill=True)

        def confirm_ingestion_job(self, job_id: str, *, initialize_missing_templates: bool = False) -> IngestionJob:
            self.confirm_calls += 1
            raise ServerError("confirm conflict", status_code=409)

        def close(self) -> None:
            pass

    transport = MockTransport()
    client = OliraClient(api_key="key", async_flush=False)
    client._transport = transport  # type: ignore[assignment]
    client._worker = None

    job = client.confirm_ingestion_job(job_id="job_1", skip_backfill=True)
    assert job.status == IngestionJobStatus.REPLAYING
    assert transport.patch_calls == 1
    assert transport.confirm_calls == 1
    client.close()
