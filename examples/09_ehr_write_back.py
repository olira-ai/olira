"""
Olira SDK — EHR Write-Back

Request that logged events also be written back into the org's connected EHR
(e.g. a home-monitoring vitals reading pushed into Epic as an Observation):
  - write_back=True on log() and LogSpec/log_batch()
  - write_back_integration_id to target a specific integration instance when
    the org runs several of the same type (e.g. Epic for two hospitals)

Write-back is a REQUEST, not a grant. The write fires only when:
  1. the API key carries the sdk:integration-write scope, AND
  2. an Olira admin has write-configured the integration for the log type.
Otherwise it is a silent no-op — the log still ingests into Olira normally,
and the API response is identical either way. Target selection without an
explicit id: single write-configured integration → inferred; several → the
patient's integration-linked identifiers decide; ambiguous → no write
(server-side warning, never a guess).

Find an integration's id (there are no typed wrappers yet):
  curl -H "Authorization: Bearer $OLIRA_API_KEY" \
    https://api.olira.ai/app-api/v1/integrations
Then set WRITE_BACK_INTEGRATION_ID in .env to target it explicitly.

Requires: sdk:event-log + sdk:integration-write scopes (logging & write-back)
          + api:manage-patients scope (patient setup)
Run: python 09_ehr_write_back.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import (  # noqa: E402
    DEFAULT_BASE_URL,
    LogSpec,
    OliraClient,
    OliraEnv,
    OliraLogType,
)

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)
# Optional: the target integration instance id (from GET /v1/integrations).
# Leave unset when your org has a single write-configured integration.
INTEGRATION_ID = os.environ.get("WRITE_BACK_INTEGRATION_ID")

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
)

# Setup — a demo patient. In real use, write-back targets patients that exist
# in the EHR: either synced from its roster or chart-linked via Patient.Create.
patient = client.create_patient(
    first_name="Writeback",
    last_name="Demo",
    timezone="UTC",
)
PID = patient.id
print(f"Demo patient: {PID}")

# ── write_back on log() — background queue ───────────────────────────────────
# The vitals reading ingests into Olira normally AND is requested for
# write-back into the EHR (as a FHIR Observation, composed by the platform).
client.log(
    log_type=OliraLogType.VITALS_MEASUREMENT,
    patient_id=PID,
    payload={
        "measurements": {"weight_kg": 72.5, "systolic_bp_mmhg": 118, "diastolic_bp_mmhg": 76},
        "collection_datetime": "2026-07-10T08:00:00Z",
    },
    write_back=True,
    write_back_integration_id=INTEGRATION_ID,  # None → platform infers the target
)
client.flush()
print("Queued vitals log with write_back=True")

# ── write_back on log_batch() — per-event control ────────────────────────────
# Only flagged events are considered for write-back; the rest ingest as usual.
result = client.log_batch(
    [
        LogSpec(
            log_type=OliraLogType.VITALS_MEASUREMENT,
            patient_id=PID,
            payload={
                "measurements": {"spo2_percent": 97},
                "collection_datetime": "2026-07-10T09:00:00Z",
            },
            write_back=True,
            write_back_integration_id=INTEGRATION_ID,
        ),
        LogSpec(  # ingest-only — no write-back requested
            log_type=OliraLogType.USER_LOGIN,
            patient_id=PID,
        ),
    ]
)
print(f"Batch: accepted={result.accepted} failed={result.failed}")
print(
    "Note: the response never reveals whether a write-back fired — verify in the "
    "EHR or the Olira Console's write-requests view (platform admins)."
)

client.close()
