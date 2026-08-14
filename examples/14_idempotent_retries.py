"""
Olira SDK — Safe Retries with idempotency_key

log_batch() (via LogSpec.idempotency_key) and log_fhir() both accept an optional
idempotency_key — log()'s background-queue path does not. Set it whenever you
might retry the same call — after a network timeout, a 5xx response, or any
client-side retry logic. Resending the same key with the same content is a
safe no-op: Olira recognizes the duplicate and does not create a second event
or re-apply patient-state updates.

Also covers:
  - log_fhir() when one submitted resource becomes several Olira events (still one key)

Requires: sdk:event-log scope (logging) + api:manage-patients scope (patient setup)
Run: python 14_idempotent_retries.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import DEFAULT_BASE_URL, LogSpec, OliraClient, OliraEnv, OliraLogType  # noqa: E402

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
    async_flush=False,
)

# Setup — create a demo patient
patient = client.create_patient(first_name="Retry", last_name="Demo", timezone="America/New_York")
PID = patient.id
print(f"Demo patient: {PID}")

# ── log_batch() retry ─────────────────────────────────────────────────────────
# Same idempotency_key sent twice: both calls return the same accepted count, and
# only one EventLog is ever created — safe to retry after a timeout or 5xx.
retry_key = "vitals-2026-01-15-0900"
spec = LogSpec(
    log_type=OliraLogType.VITALS_MEASUREMENT,
    patient_id=PID,
    payload={"measurements": {"heart_rate_bpm": 72, "spo2_percent": 98}},
    idempotency_key=retry_key,
)
result = client.log_batch([spec])
print(f"log_batch (1st call)  — accepted={result.accepted}")
result = client.log_batch([spec])
print(f"log_batch (2nd call)  — accepted={result.accepted}  (deduped, no new EventLog created)")

# ── log_fhir() retry ──────────────────────────────────────────────────────────
# Same pattern for FHIR resources — but here an explicit key isn't just
# recommended, it's the real safety net. The no-key content-hash fallback only
# works when the timestamp is stable across the resend; when the source
# resource has no usable date, the timestamp defaults to wall-clock time at
# processing, which differs on every retry and silently defeats the fallback.
# Always pass idempotency_key for any log_fhir() call you might retry.
fhir_retry_key = "condition-2026-01-10"
condition_resource = {
    "resourceType": "Condition",
    "id": "condition-retry-demo",
    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006", "display": "Type 2 diabetes"}]},
    "subject": {"reference": f"Patient/{PID}"},
}
result = client.log_fhir(patient_id=PID, resource=condition_resource, idempotency_key=fhir_retry_key)
print(f"log_fhir (1st call)   — accepted={result.accepted}")
result = client.log_fhir(patient_id=PID, resource=condition_resource, idempotency_key=fhir_retry_key)
print(f"log_fhir (2nd call)   — accepted={result.accepted}  (deduped, no new EventLog created)")

# ── log_fhir() — one resource, several events ─────────────────────────────────
# Some EHR records become more than one Olira event. This example sends a
# treatment plan; Olira turns it into a follow-up item and a treatment-phase
# update. Still pass one idempotency_key; retry with that same string.
treatment_plan = {
    "resourceType": "CarePlan",
    "id": "plan-retry-demo",
    "status": "active",
    "intent": "plan",
    "subject": {"reference": f"Patient/{PID}"},
    "category": [
        {"coding": [{"system": "http://hl7.org/fhir/us/core/CodeSystem/careplan-category", "code": "assess-plan"}]}
    ],
    "activity": [{"detail": {"description": "Follow-up oncology visit in 4 weeks"}}],
}
plan_key = "plan-2026-01-10"
result = client.log_fhir(patient_id=PID, resource=treatment_plan, idempotency_key=plan_key)
print(f"log_fhir (several events) — accepted={result.accepted} from one resource")
result = client.log_fhir(patient_id=PID, resource=treatment_plan, idempotency_key=plan_key)
print(f"log_fhir retry            — accepted={result.accepted}  (no new events)")

# ── Demo cleanup — remove the test patient so your org stays clean ────────────
# Not part of a real integration.
client.delete_patient(patient_id=PID)
client.close()
print("Done.")
