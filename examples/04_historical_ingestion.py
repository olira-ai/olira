"""
Olira SDK — Historical Data Ingestion

Two paths to bulk-load existing patient data before going live:

  Path A — File upload (recommended for large datasets)
    SDK uploads a JSONL file to S3 and creates the ingestion job in one call.
    No size cap beyond the org limit (default 100 MB, configurable server-side).

  Path B — Inline records (for smaller datasets built programmatically)
    Pass a list of IngestRecord objects directly — no file on disk needed.
    Capped at 50,000 records per job. Optional OliraTrace on individual logs.

Both paths go through the same pipeline:
  QUEUED → VALIDATING → INSERTING_PATIENTS → INSERTING_LOGS → AWAITING_CONFIRMATION
  (then, after confirm)
  EXTRACTING → REPLAYING → LOADING → REBASING → EMBEDDING → BACKFILLING → COMPLETED
  (EXTRACTING / REBASING / EMBEDDING are skipped when the job has nothing for that stage)

Requires: sdk:historical-ingest scope
Run: python 04_historical_ingestion.py
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import (  # noqa: E402
    DEFAULT_BASE_URL,
    CreatePatientRequest,
    ExternalIdentifier,
    IngestLogSpec,
    IngestRecord,
    OliraClient,
    OliraEnv,
    OliraTrace,
)

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
    async_flush=False,  # ingestion uses direct HTTP calls, not the background log queue
)


def poll_until(client, job_id, target_statuses, interval=10, timeout=300):
    """Poll get_ingestion_job until status is in target_statuses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get_ingestion_job(job_id=job_id)
        eta = f"  ETA ~{job.estimated_seconds_remaining}s" if job.estimated_seconds_remaining else ""
        print(f"  [{job.status}] {job.progress_pct:.0f}%  {job.stage}{eta}")
        if job.status in target_statuses:
            return job
        time.sleep(interval)
    raise TimeoutError(f"Job {job_id} did not reach {target_statuses} within {timeout}s")


# ── Path A: File upload ────────────────────────────────────────────────────────

JSONL_FILE = Path(__file__).parent / "sample_data.jsonl"

# Write a minimal sample file if one doesn't exist
if not JSONL_FILE.exists():
    import json

    lines = [
        {
            "type": "patient",
            "data": {
                "first_name": "Jane",
                "last_name": "FileDemo",
                "timezone": "UTC",
                "external_identifiers": [{"system": "demo", "value": "FILE-001"}],
            },
        },
        {
            "type": "log",
            "data": {
                "event_type": "moods_report",
                "patient_id": "FILE-001",
                "timestamp": "2025-06-01T09:00:00Z",
                "payload": {"moods": [{"mood": "hopeful", "intensity": 6}], "source": "checkin"},
                "idempotency_key": "file-001-mood-01",
                "trace": {"object_type": "emr_record", "object_id": "epic-encounter-98765"},
            },
        },
    ]
    JSONL_FILE.write_text("\n".join(json.dumps(row) for row in lines))
    print(f"Created sample file: {JSONL_FILE}")

print("\n── Path A: File upload ──")
job = client.create_ingestion_job(
    file=str(JSONL_FILE),
    idempotency_key="demo-file-upload-2026",
    require_confirmation=True,
    summary_types=["emotional_state_snapshot"],  # only backfill this view type
)
print(f"Job created: {job.job_id} (status={job.status})")

# Poll Phase 1 — wait for AWAITING_CONFIRMATION
job = poll_until(client, job.job_id, {"awaiting_confirmation", "failed", "completed"}, interval=5)

if job.status == "awaiting_confirmation":
    print("\nReview summary:")
    print(f"  Patients processed : {job.patients_processed}")
    print(f"  Logs inserted      : {job.logs_processed}  (failed: {job.logs_failed})")
    print(f"  By event type      : {job.logs_by_event_type}")
    if job.error_summary:
        for err in job.error_summary:
            print(f"  Error  line {err.line}: [{err.code}] {err.message}")

    # Confirm to start Phase 2 (graph replay + view backfill)
    job = client.confirm_ingestion_job(job_id=job.job_id)
    print("\nConfirmed — Phase 2 started, polling…")
    job = poll_until(client, job.job_id, {"completed", "completed_with_errors", "failed"}, interval=15)
    print(f"\nFinal status: {job.status}  (tokens_used={job.tokens_used})")
elif job.status == "failed":
    print(f"Job FAILED: {job.error_summary[:3]}")


# ── Path B: Inline records ─────────────────────────────────────────────────────

print("\n── Path B: Inline records ──")
records = [
    IngestRecord.patient(
        CreatePatientRequest(
            first_name="Bob",
            last_name="InlineDemo",
            timezone="America/New_York",
            external_identifiers=[ExternalIdentifier(system="demo", value="INLINE-002")],
        )
    ),
    IngestRecord.log(
        IngestLogSpec(
            event_type="symptom_report",
            patient_id="INLINE-002",  # matches external_identifier value above
            timestamp="2025-07-15T10:00:00Z",
            payload={
                "instrument": "esas_r",
                "symptoms": [{"name": "fatigue", "score": 5}, {"name": "pain", "score": 3}],
            },
            idempotency_key="inline-002-symptom-01",
            trace=OliraTrace(object_type="emr_record", object_id="epic-encounter-98765"),
        )
    ),
    IngestRecord.log(
        IngestLogSpec(
            event_type="moods_report",
            patient_id="INLINE-002",
            timestamp="2025-07-16T08:30:00Z",
            payload={"moods": [{"mood": "anxious", "intensity": 4}], "source": "checkin"},
            idempotency_key="inline-002-mood-01",
        )
    ),
]

# require_confirmation=False — run straight through without a review pause
job = client.create_ingestion_job(
    records=records,
    idempotency_key="demo-inline-2026",
    require_confirmation=False,
)
print(f"Job created: {job.job_id} (status={job.status})")
job = poll_until(client, job.job_id, {"completed", "completed_with_errors", "failed"}, interval=10)
print(f"Final status: {job.status}")
print(f"  patient_replay_statuses: {job.patient_replay_statuses}")

client.close()
