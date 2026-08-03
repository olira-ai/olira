"""Tests for the passive signal ingestion SDK surface (send_signals + SignalJobHandle)."""

import hashlib
import json

import pytest

import olira
from olira.signals import (
    DEFAULT_SYNC_BODY_CAP_BYTES,
    SignalJob,
    SignalJobHandle,
    SignalJobStatus,
    SignalSensorType,
    send_signals_via_transport,
    serialize_signal_records,
)

RECORDS = [
    {"ts": "2026-06-01T12:00:00+00:00", "x": 0.1, "y": 0.2, "z": 9.8},
    {"ts": "2026-06-01T12:00:01+00:00", "x": 0.0, "y": 0.1, "z": 9.7},
]


def _job_payload(job_id: str = "job-1", status: str = "received") -> dict:
    return {"job_id": job_id, "status": status, "door": "sync", "batch_ids": ["b1"]}


class MockTransport:
    """Captures signal-door calls; configurable sync cap and job states."""

    def __init__(self, *, sync_cap: int = DEFAULT_SYNC_BODY_CAP_BYTES, job_states: list[str] | None = None):
        self.sync_cap = sync_cap
        self.batch_calls: list[dict] = []
        self.upload_calls: list[dict] = []
        self.manifest_calls: list[dict] = []
        self.presigned_puts: list[tuple[str, bytes]] = []
        self.job_states = job_states or ["received"]
        self._poll_count = 0

    def get_sdk_config(self) -> dict:
        return {"signals_max_sync_body_bytes": self.sync_cap}

    def send_signal_batch(self, *, params, content, headers) -> dict:
        self.batch_calls.append({"params": params, "content": content, "headers": headers})
        return {"job_id": "job-1", "batch_id": "b1", "status": "received", "deduplicated": False}

    def get_signal_upload_urls(self, body) -> dict:
        self.upload_calls.append(body)
        return {
            "uploads": [
                {
                    "batch_id": "b-bulk",
                    "lake_key": "raw/org=o/x.parquet",
                    "upload_url": "https://s3/put",
                    "expires_in": 900,
                }
            ]
        }

    def put_presigned(
        self, url: str, blob: bytes, headers: dict[str, str] | None = None
    ) -> None:
        self.presigned_puts.append((url, blob))

    def commit_signal_manifest(self, body) -> SignalJob:
        self.manifest_calls.append(body)
        return SignalJob.model_validate(_job_payload("job-bulk"))

    def get_signal_job(self, job_id: str) -> SignalJob:
        state = self.job_states[min(self._poll_count, len(self.job_states) - 1)]
        self._poll_count += 1
        return SignalJob.model_validate(_job_payload(job_id, state))


def test_serialize_signal_records_round_trips():
    blob = serialize_signal_records(RECORDS)
    import io

    import pyarrow.parquet as pq

    table = pq.read_table(io.BytesIO(blob))
    assert table.num_rows == 2
    assert set(table.column_names) == {"ts", "x", "y", "z"}


def test_serialize_empty_records_raises():
    with pytest.raises(olira.ValidationError):
        serialize_signal_records([])


def test_send_signals_requires_exactly_one_payload():
    transport = MockTransport()
    with pytest.raises(olira.ValidationError):
        send_signals_via_transport(transport, patient_id="p", sensor_type="accelerometer", source_device="d")
    with pytest.raises(olira.ValidationError):
        send_signals_via_transport(
            transport,
            patient_id="p",
            sensor_type="accelerometer",
            source_device="d",
            records=RECORDS,
            parquet=b"x",
        )


def test_send_signals_rejects_unknown_sensor():
    with pytest.raises(ValueError):
        send_signals_via_transport(
            MockTransport(), patient_id="p", sensor_type="heart-rate", source_device="d", records=RECORDS
        )


def test_send_signals_small_payload_uses_sync_door():
    transport = MockTransport()
    handle = send_signals_via_transport(
        transport,
        patient_id="p-1",
        sensor_type=SignalSensorType.ACCELEROMETER,
        source_device="watch-1",
        records=RECORDS,
        sample_rate_hz=50.0,
        units={"x": "g", "y": "g", "z": "g"},
    )
    assert isinstance(handle, SignalJobHandle)
    assert handle.job_id == "job-1"
    assert len(transport.batch_calls) == 1
    assert transport.upload_calls == []

    call = transport.batch_calls[0]
    assert call["params"]["patient_id"] == "p-1"
    assert call["params"]["sensor_type"] == "accelerometer"
    assert call["params"]["source_device"] == "watch-1"
    # SDK hashes the exact bytes it sends.
    assert call["headers"]["X-Content-SHA256"] == hashlib.sha256(call["content"]).hexdigest()
    metadata = json.loads(call["headers"]["X-Olira-Batch-Meta"])
    assert metadata["declared_sample_rate_hz"] == 50.0
    assert metadata["units"] == {"x": "g", "y": "g", "z": "g"}


def test_send_signals_large_payload_routes_to_bulk_door():
    transport = MockTransport(sync_cap=8)  # force the bulk path
    handle = send_signals_via_transport(
        transport,
        patient_id="p-1",
        sensor_type="gps",
        source_device="phone",
        records=[{"ts": "2026-06-01T12:00:00+00:00", "lat": 1.0, "lon": 2.0}],
    )
    assert handle.job_id == "job-bulk"
    assert transport.batch_calls == []
    assert len(transport.presigned_puts) == 1
    [manifest] = transport.manifest_calls
    file = manifest["files"][0]
    assert file["batch_id"] == "b-bulk"
    assert file["lake_key"] == "raw/org=o/x.parquet"
    assert file["content_sha256"] == hashlib.sha256(transport.presigned_puts[0][1]).hexdigest()
    assert file["size_bytes"] == len(transport.presigned_puts[0][1])


def test_send_signals_accepts_preserialized_parquet():
    transport = MockTransport()
    blob = serialize_signal_records(RECORDS)
    send_signals_via_transport(transport, patient_id="p", sensor_type="accelerometer", source_device="d", parquet=blob)
    assert transport.batch_calls[0]["content"] == blob


def test_job_handle_wait_polls_to_terminal():
    transport = MockTransport(job_states=["processing", "processing", "done"])
    job = SignalJob.model_validate(_job_payload(status="received"))
    handle = SignalJobHandle(job, transport.get_signal_job)
    final = handle.wait(timeout=5, interval=0.01)
    assert final.status == SignalJobStatus.DONE
    assert final.status.is_terminal


def test_job_handle_wait_times_out():
    transport = MockTransport(job_states=["processing"])
    handle = SignalJobHandle(SignalJob.model_validate(_job_payload()), transport.get_signal_job)
    with pytest.raises(olira.OliraError, match="not terminal"):
        handle.wait(timeout=0.05, interval=0.01)


def test_client_exposes_send_signals():
    assert hasattr(olira.OliraClient, "send_signals")
    assert hasattr(olira.OliraClient, "get_signal_job")
    assert "SignalJobHandle" in olira.__all__
