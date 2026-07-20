"""
Olira SDK — Patient Management

Covers the full patient lifecycle:
  - Create with full demographics
  - Create a shell patient (external ID only)
  - Batch create up to 500 patients at once
  - Look up by external identifier
  - Update demographics
  - Soft-delete

Requires: api:manage-patients scope
Run: python 01_patient_management.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import DEFAULT_BASE_URL, CreatePatientRequest, ExternalIdentifier, OliraClient, OliraEnv  # noqa: E402

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
    async_flush=False,  # this example doesn't use log() — disable the background queue thread
    # project="dev-sandbox",  # ← isolate every patient op to a project (workspace).
    #   Omit for the org's default project. Patients created here are invisible to
    #   other projects, and list_patients() returns only this project's patients.
    #   See examples/10_project_management.py and SDK_DOCUMENTATION.md#projects.
)

created_ids: list[str] = []

# ── Full demographics ──────────────────────────────────────────────────────────
patient = client.create_patient(
    first_name="Alice",
    last_name="Nguyen",
    date_of_birth="1978-09-03T00:00:00Z",
    sex="female",
    timezone="America/Chicago",
    primary_disease_site="breast",
    disease_stage="Stage II",
    external_identifiers=[ExternalIdentifier(system="epic", value="MRN-10001")],
    metadata={"trial_arm": "A", "site": "CHI-01"},
)
created_ids.append(patient.id)
print(f"Created patient: {patient.id} — {patient.first_name} {patient.last_name}")

# ── Shell patient — external ID only, no demographics yet ────────────────────
# Useful when you only have a system ID and will sync demographics later.
shell = client.create_patient(
    external_identifiers=[ExternalIdentifier(system="flatiron", value="FLT-99002")],
)
created_ids.append(shell.id)
print(f"Shell patient:  {shell.id} (no name yet)")

# ── Update — fill in demographics after the fact ─────────────────────────────
updated = client.update_patient(
    patient_id=shell.id,
    first_name="Bob",
    last_name="Chen",
    date_of_birth="1990-02-14T00:00:00Z",
    timezone="America/Los_Angeles",
)
print(f"Updated shell:  {updated.first_name} {updated.last_name}")

# ── Look up by external identifier ───────────────────────────────────────────
result = client.list_patients(external_system="epic", external_value="MRN-10001")
if result.patients:
    found = result.patients[0]
    print(f"Lookup by EID:  found {found.id} ({found.first_name} {found.last_name})")

# ── Batch create — up to 500 patients in one call ────────────────────────────
batch_result = client.create_patients_batch(
    [
        CreatePatientRequest(
            first_name="Carol",
            last_name="Davis",
            timezone="UTC",
            external_identifiers=[ExternalIdentifier(system="epic", value="BATCH-C001")],
        ),
        CreatePatientRequest(
            first_name="David",
            last_name="Park",
            timezone="UTC",
            external_identifiers=[ExternalIdentifier(system="epic", value="BATCH-D002")],
        ),
    ]
)
created_ids.extend(item.id for item in batch_result.items)
print(f"Batch create:   {batch_result.count} created, {len(batch_result.errors)} errors")

# ── Demo cleanup — remove test patients so your org stays clean ───────────────
# Not part of a real integration.
for pid in created_ids:
    client.delete_patient(patient_id=pid)
client.close()
print(f"Cleaned up {len(created_ids)} patients.")
