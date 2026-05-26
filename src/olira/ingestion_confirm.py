"""Retry-safe helpers for ingestion job confirm (PATCH skip_backfill + POST confirm)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .exceptions import ServerError
from .models import IngestionJob, IngestionJobStatus

# Phase 1 only
_PHASE1_BEFORE_REVIEW_STATUSES = frozenset(
    {
        IngestionJobStatus.QUEUED.value,
        IngestionJobStatus.VALIDATING.value,
        IngestionJobStatus.INSERTING_PATIENTS.value,
        IngestionJobStatus.INSERTING_LOGS.value,
    }
)


def _status_value(status: IngestionJobStatus | str) -> str:
    return status.value if isinstance(status, IngestionJobStatus) else status


def is_409_past_review_gate(status: IngestionJobStatus | str) -> bool:
    """True when a PATCH/confirm HTTP 409 means the job already left the review gate.

    The API returns 409 whenever status is not ``AWAITING_CONFIRMATION``. That includes
    successful confirm retries (``replaying``, ``completed``, …) and terminal outcomes
    after review (``cancelled``, ``failed``). Phase-1 statuses mean the call was too early,
    not a retried confirm — those 409s should be re-raised.
    """
    s = _status_value(status)
    if s in _PHASE1_BEFORE_REVIEW_STATUSES:
        return False
    if s == IngestionJobStatus.AWAITING_CONFIRMATION.value:
        return False
    return True


def is_post_confirmation_status(status: IngestionJobStatus | str) -> bool:
    """Backward-compatible alias; prefer :func:`is_409_past_review_gate`."""
    return is_409_past_review_gate(status)


def ensure_skip_backfill_before_confirm(
    *,
    patch_skip_backfill: Callable[[], IngestionJob],
    get_job: Callable[[], IngestionJob],
) -> None:
    """PATCH ``skip_backfill=True``, tolerating 409 if the job already advanced past review."""
    try:
        patch_skip_backfill()
    except ServerError as exc:
        if exc.status_code != 409:
            raise
        job = get_job()
        if not is_409_past_review_gate(job.status):
            raise


async def ensure_skip_backfill_before_confirm_async(
    *,
    patch_skip_backfill: Callable[[], Awaitable[IngestionJob]],
    get_job: Callable[[], Awaitable[IngestionJob]],
) -> None:
    try:
        await patch_skip_backfill()
    except ServerError as exc:
        if exc.status_code != 409:
            raise
        job = await get_job()
        if not is_409_past_review_gate(job.status):
            raise


def confirm_ingestion_job_resilient(
    *,
    skip_backfill: bool,
    patch_skip_backfill: Callable[[], IngestionJob],
    get_job: Callable[[], IngestionJob],
    confirm: Callable[[], IngestionJob],
) -> IngestionJob:
    """Confirm a job; tolerate retried PATCH/confirm after the server already transitioned."""
    if skip_backfill:
        ensure_skip_backfill_before_confirm(
            patch_skip_backfill=patch_skip_backfill,
            get_job=get_job,
        )
    try:
        return confirm()
    except ServerError as exc:
        if exc.status_code != 409:
            raise
        job = get_job()
        if is_409_past_review_gate(job.status):
            return job
        raise


async def confirm_ingestion_job_resilient_async(
    *,
    skip_backfill: bool,
    patch_skip_backfill: Callable[[], Awaitable[IngestionJob]],
    get_job: Callable[[], Awaitable[IngestionJob]],
    confirm: Callable[[], Awaitable[IngestionJob]],
) -> IngestionJob:
    if skip_backfill:
        await ensure_skip_backfill_before_confirm_async(
            patch_skip_backfill=patch_skip_backfill,
            get_job=get_job,
        )
    try:
        return await confirm()
    except ServerError as exc:
        if exc.status_code != 409:
            raise
        job = await get_job()
        if is_409_past_review_gate(job.status):
            return job
        raise
