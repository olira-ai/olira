"""
Olira SDK — FHIR R4 Ingestion

log_fhir() accepts a single FHIR R4 resource and maps it to Olira log types
using the same absorber as Epic/Cerner integrations. You don't choose a
log_type or build Olira-shaped payloads — the absorber handles the mapping.

Also covers:
  - Error handling for unsupported resource types
  - Error handling for missing resourceType

Requires: sdk:event-log scope (FHIR ingest) + api:manage-patients scope (patient setup)
Run: python 03_fhir_ingestion.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import ExternalIdentifier, OliraClient, OliraEnv, ValidationError  # noqa: E402

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", "https://api.prod.olira.ai")

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
    async_flush=False,
)

# Setup — create a demo patient
patient = client.create_patient(
    first_name="FHIR",
    last_name="Demo",
    timezone="America/New_York",
    external_identifiers=[ExternalIdentifier(system="demo", value="FHIR-DEMO-001")],
)
PID = patient.id
print(f"Demo patient: {PID}")

# ── Condition ─────────────────────────────────────────────────────────────────
result = client.log_fhir(
    patient_id=PID,
    resource={
        "resourceType": "Condition",
        "id": "condition-1",
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}],
        },
        "code": {
            "coding": [{"system": "http://snomed.info/sct", "code": "254837009", "display": "Breast cancer"}],
            "text": "Breast cancer",
        },
        "subject": {"reference": f"Patient/{PID}"},
        "onsetDateTime": "2025-01-10T00:00:00Z",
    },
)
print(f"Condition        — accepted={result.accepted}")

# ── MedicationRequest ─────────────────────────────────────────────────────────
result = client.log_fhir(
    patient_id=PID,
    resource={
        "resourceType": "MedicationRequest",
        "id": "med-1",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "1049502"}],
            "text": "Ondansetron 4mg",
        },
        "subject": {"reference": f"Patient/{PID}"},
        "authoredOn": "2025-03-01T00:00:00Z",
        "dosageInstruction": [{"text": "4mg orally every 8 hours as needed"}],
    },
)
print(f"MedicationRequest — accepted={result.accepted}")

# ── Appointment ───────────────────────────────────────────────────────────────
result = client.log_fhir(
    patient_id=PID,
    resource={
        "resourceType": "Appointment",
        "id": "appt-1",
        "status": "booked",
        "serviceType": [{"coding": [{"code": "oncology", "display": "Oncology"}]}],
        "start": "2026-06-15T09:00:00Z",
        "end": "2026-06-15T09:30:00Z",
        "participant": [{"actor": {"reference": f"Patient/{PID}"}, "status": "accepted"}],
    },
)
print(f"Appointment       — accepted={result.accepted}")

# ── Error handling — unsupported resource type ────────────────────────────────
try:
    client.log_fhir(
        patient_id=PID,
        resource={"resourceType": "SupplyDelivery", "status": "completed"},
    )
except ValidationError as e:
    print(f"Unsupported type  — ValidationError: {e}")

# ── Error handling — missing resourceType ────────────────────────────────────
try:
    client.log_fhir(
        patient_id=PID,
        resource={"status": "final", "code": {"text": "BP"}},
    )
except ValidationError as e:
    print(f"Missing type      — ValidationError: {e}")

# ── Demo cleanup — remove the test patient so your org stays clean ────────────
# Not part of a real integration.
client.delete_patient(patient_id=PID)
client.close()
print("Done.")
