"""Retry-safe helpers for ingestion job confirm (PATCH skip_backfill + POST confirm)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .exceptions import ServerError
from .models import IngestionJob, IngestionJobStatus

# Job has left AWAITING_CONFIRMATION after a successful confirm (or is finishing).
_POST_CONFIRM_STATUSES = frozenset(
    {
        IngestionJobStatus.CONFIRMED.value,
        IngestionJobStatus.REPLAYING.value,
        IngestionJobStatus.BACKFILLING.value,
        IngestionJobStatus.COMPLETED.value,
        IngestionJobStatus.COMPLETED_WITH_ERRORS.value,
    }
)


def _status_value(status: IngestionJobStatus | str) -> str:
    return status.value if isinstance(status, IngestionJobStatus) else status


def is_post_confirmation_status(status: IngestionJobStatus | str) -> bool:
    """True when the job has already been confirmed and Phase 2 has started or finished."""
    return _status_value(status) in _POST_CONFIRM_STATUSES


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
        if not is_post_confirmation_status(job.status):
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
        if not is_post_confirmation_status(job.status):
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
        if is_post_confirmation_status(job.status):
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
        if is_post_confirmation_status(job.status):
            return job
        raise
