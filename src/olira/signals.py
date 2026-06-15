"""Passive signal ingestion: send accelerometer / gyroscope / GPS batches to Olira.

One call — :meth:`olira.OliraClient.send_signals` — serializes records to Parquet, hashes
them, stamps the schema version, measures the payload, and routes automatically:

- small/medium payloads → synchronous ``POST /v1/signals:batch``
- large payloads → presigned S3 PUT + ``POST /v1/signals:manifest``

Requires the ``sdk:event-log`` API-key scope (the same capability as event logging)
and the optional ``pyarrow`` dependency
(``pip install olira[signals]``) unless you pass pre-serialized Parquet bytes.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from .exceptions import OliraError, ValidationError

if TYPE_CHECKING:
    from .http import HttpTransport

#: Fallback sync-door body cap when GET /v1/sdk/config is unavailable. The server
#: enforces the real limit; this only picks the routing.
DEFAULT_SYNC_BODY_CAP_BYTES = 32 * 1024 * 1024


class SignalSensorType(StrEnum):
    """Sensors accepted by the v1 signal ingestion doors."""

    ACCELEROMETER = "accelerometer"
    GYROSCOPE = "gyroscope"
    GPS = "gps"


class SignalJobStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (SignalJobStatus.DONE, SignalJobStatus.PARTIAL, SignalJobStatus.FAILED)


class SignalJob(BaseModel):
    """A signal ingestion job returned by the API."""

    job_id: str
    status: SignalJobStatus
    door: str = "sync"
    batch_ids: list[str] = Field(default_factory=list)
    batch_statuses: dict[str, str] = Field(default_factory=dict)
    batch_progress: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="batch_id -> {written, total_rows} absorption checkpoints while a large batch processes.",
    )
    progress_pct: float | None = Field(
        default=None, description="Percent of rows absorbed (large batches report while processing)."
    )
    records_decoded: int = 0
    records_valid: int = 0
    records_quarantined: int = 0
    records_deduplicated: int = 0
    records_written: int = 0
    error_summary: list[str] = Field(default_factory=list)
    created_at: str | None = None
    completed_at: str | None = None
    deduplicated: bool = Field(default=False, description="True when the upload was a content-hash no-op.")


class SignalJobHandle:
    """Poll/wait handle for a signal ingestion job."""

    def __init__(self, job: SignalJob, fetch: Callable[[str], SignalJob]):
        self._job = job
        self._fetch = fetch

    @property
    def job_id(self) -> str:
        return self._job.job_id

    @property
    def job(self) -> SignalJob:
        return self._job

    def poll(self) -> SignalJob:
        """Refresh and return the current job state."""
        self._job = self._fetch(self._job.job_id)
        return self._job

    def wait(self, *, timeout: float = 300.0, interval: float = 2.0) -> SignalJob:
        """Block until the job reaches a terminal status (done / partial / failed)."""
        deadline = time.monotonic() + timeout
        job = self.poll()
        while not job.status.is_terminal:
            if time.monotonic() > deadline:
                raise OliraError(f"Signal job {job.job_id} not terminal after {timeout}s (status={job.status})")
            time.sleep(interval)
            job = self.poll()
        return job


def serialize_signal_records(records: list[dict[str, Any]]) -> bytes:
    """Serialize measurement rows (each with a 'ts' key) to a Parquet blob.

    Requires pyarrow: ``pip install olira[signals]``.
    """
    if not records:
        raise ValidationError("records must be a non-empty list")
    try:
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise OliraError(
            "pyarrow is required to serialize signal records — install with: pip install olira[signals]"
        ) from exc

    import io  # noqa: PLC0415

    table = pa.Table.from_pylist(records)
    sink = io.BytesIO()
    pq.write_table(table, sink)  # type: ignore[no-untyped-call]
    return sink.getvalue()


def _build_batch_metadata(
    *,
    sample_rate_hz: float | None,
    units: dict[str, str] | None,
    timestamp_unit: str | None,
    device_timezone: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if sample_rate_hz is not None:
        metadata["declared_sample_rate_hz"] = sample_rate_hz
    if units:
        metadata["units"] = units
    if timestamp_unit:
        metadata["timestamp_unit"] = timestamp_unit
    if device_timezone:
        metadata["device_timezone"] = device_timezone
    return metadata


def send_signals_via_transport(
    transport: HttpTransport,
    *,
    patient_id: str,
    sensor_type: SignalSensorType | str,
    source_device: str,
    records: list[dict[str, Any]] | None = None,
    parquet: bytes | None = None,
    schema_version: str | None = None,
    sample_rate_hz: float | None = None,
    units: dict[str, str] | None = None,
    timestamp_unit: str | None = None,
    device_timezone: str | None = None,
) -> SignalJobHandle:
    """Shared implementation behind :meth:`olira.OliraClient.send_signals`."""
    if (records is None) == (parquet is None):
        raise ValidationError("Provide exactly one of 'records' or 'parquet'")
    sensor = SignalSensorType(sensor_type)
    blob = parquet if parquet is not None else serialize_signal_records(records or [])
    sha256 = hashlib.sha256(blob).hexdigest()
    metadata = _build_batch_metadata(
        sample_rate_hz=sample_rate_hz,
        units=units,
        timestamp_unit=timestamp_unit,
        device_timezone=device_timezone,
    )

    try:
        sdk_config = transport.get_sdk_config()
        sync_cap = int(sdk_config.get("signals_max_sync_body_bytes", DEFAULT_SYNC_BODY_CAP_BYTES))
    except Exception:  # noqa: BLE001 - config fetch is best-effort; the server still enforces
        sync_cap = DEFAULT_SYNC_BODY_CAP_BYTES

    descriptor: dict[str, Any] = {
        "patient_id": patient_id,
        "sensor_type": sensor.value,
        "source_device": source_device,
        "content_sha256": sha256,
        "size_bytes": len(blob),
        "batch_metadata": metadata,
    }
    if schema_version:
        descriptor["schema_version"] = schema_version

    if len(blob) <= sync_cap:
        params = {
            "patient_id": patient_id,
            "sensor_type": sensor.value,
            "source_device": source_device,
        }
        if schema_version:
            params["schema_version"] = schema_version
        headers = {
            "X-Content-SHA256": sha256,
            "Content-Type": "application/vnd.apache.parquet",
        }
        if metadata:
            headers["X-Olira-Batch-Meta"] = json.dumps(metadata)
        raw = transport.send_signal_batch(params=params, content=blob, headers=headers)
        job = transport.get_signal_job(raw["job_id"])
        job.deduplicated = bool(raw.get("deduplicated", False))
        return SignalJobHandle(job, transport.get_signal_job)

    # Bulk path: presigned PUT + manifest commit.
    upload = transport.get_signal_upload_urls({"files": [descriptor]})["uploads"][0]
    transport.put_presigned(upload["upload_url"], blob)
    manifest_file = {**descriptor, "batch_id": upload["batch_id"], "lake_key": upload["lake_key"]}
    job = transport.commit_signal_manifest({"files": [manifest_file]})
    return SignalJobHandle(job, transport.get_signal_job)
