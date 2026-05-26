"""
Olira SDK — Logs-Only Ingestion Workflow

Common use case: patients already exist in your org (created via create_patients_batch
or the Console), and you want to ingest historical logs for them without re-creating
the patient records.

The ingestion job's Stage 3 resolves patient_id values against existing org patients
by external_identifier — no patient records needed in the JSONL.

Steps:
  1. Create patients in advance via create_patients_batch()
  2. Submit an ingestion job containing only log records
  3. Confirm and poll to COMPLETED

Requires: api:manage-patients + sdk:historical-ingest scopes
Run: python 05_logs_only_workflow.py
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
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get_ingestion_job(job_id=job_id)
        print(f"  [{job.status}] {job.progress_pct:.0f}%  {job.stage}")
        if job.status in target_statuses:
            return job
        time.sleep(interval)
    raise TimeoutError(f"Job {job_id} did not reach {target_statuses} within {timeout}s")


# ── Step 1: Create patients upfront via batch API ─────────────────────────────
print("Step 1: Creating patients via create_patients_batch()…")
batch = client.create_patients_batch(
    [
        CreatePatientRequest(
            first_name="Emma",
            last_name="Rossi",
            date_of_birth="1972-11-20T00:00:00Z",
            timezone="America/New_York",
            external_identifiers=[ExternalIdentifier(system="epic", value="LOGS-ONLY-E001")],
        ),
        CreatePatientRequest(
            first_name="Marco",
            last_name="Silva",
            date_of_birth="1985-03-07T00:00:00Z",
            timezone="America/Chicago",
            external_identifiers=[ExternalIdentifier(system="epic", value="LOGS-ONLY-M002")],
        ),
    ]
)
patient_ids = [item.id for item in batch.items]
print(f"  Created {batch.count} patients: {[i[:8] + '…' for i in patient_ids]}")

# ── Step 2: Submit logs-only ingestion job ─────────────────────────────────────
# patient_id in each log uses the external_identifier value ("LOGS-ONLY-E001" etc.)
# Stage 3 resolves these against the org's existing patients — no patient records needed.
print("\nStep 2: Submitting logs-only ingestion job…")
records = [
    IngestRecord.log(
        IngestLogSpec(
            event_type="symptom_report",
            patient_id="LOGS-ONLY-E001",  # external_identifier value
            timestamp="2025-01-10T09:00:00Z",
            payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 5}]},
            idempotency_key="e001-symptom-2025-01-10",
        )
    ),
    IngestRecord.log(
        IngestLogSpec(
            event_type="moods_report",
            patient_id="LOGS-ONLY-E001",
            timestamp="2025-01-11T08:00:00Z",
            payload={"moods": [{"mood": "tired", "intensity": 6}], "source": "checkin"},
            idempotency_key="e001-mood-2025-01-11",
        )
    ),
    IngestRecord.log(
        IngestLogSpec(
            event_type="symptom_report",
            patient_id="LOGS-ONLY-M002",
            timestamp="2025-02-05T14:00:00Z",
            payload={"instrument": "esas_r", "symptoms": [{"name": "nausea", "score": 3}]},
            idempotency_key="m002-symptom-2025-02-05",
        )
    ),
    IngestRecord.log(
        IngestLogSpec(
            event_type="moods_report",
            patient_id="LOGS-ONLY-M002",
            timestamp="2025-02-06T09:00:00Z",
            payload={"moods": [{"mood": "calm", "intensity": 7}], "source": "checkin"},
            idempotency_key="m002-mood-2025-02-06",
        )
    ),
]

job = client.create_ingestion_job(
    records=records,
    idempotency_key="logs-only-demo-2026",
    require_confirmation=True,
)
print(f"  Job created: {job.job_id} (status={job.status})")

# ── Step 3: Review and confirm ─────────────────────────────────────────────────
print("\nStep 3: Polling to AWAITING_CONFIRMATION…")
job = poll_until(client, job.job_id, {"awaiting_confirmation", "failed"}, interval=5)

if job.status == "awaiting_confirmation":
    print(f"\n  patients_processed : {job.patients_processed}  (expected 0 — no patient records in file)")
    print(f"  logs_processed     : {job.logs_processed}")
    print(f"  logs_failed        : {job.logs_failed}")
    if job.error_summary:
        for e in job.error_summary:
            print(f"  Error: [{e.code}] {e.message}")

    job = client.confirm_ingestion_job(job_id=job.job_id)
    print("\nConfirmed — polling to COMPLETED…")
    job = poll_until(client, job.job_id, {"completed", "completed_with_errors", "failed"}, interval=15)
    print(f"\nFinal: {job.status}  replay_statuses={job.patient_replay_statuses}")

# ── Demo cleanup — remove test patients so your org stays clean ───────────────
# Not part of a real integration.
for pid in patient_ids:
    client.delete_patient(patient_id=pid)
client.close()
print(f"\nCleaned up {len(patient_ids)} patients.")
