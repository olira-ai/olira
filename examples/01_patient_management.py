"""
Olira SDK — Patient Management

Covers the full patient lifecycle:
  - Create with full demographics
  - Create a shell patient (external ID only)
  - Batch create up to 500 patients at once
  - Look up by external identifier
  - Update demographics
  - Delete — soft (default) vs. permanent (hard-delete + cascade)

Requires: api:manage-patients scope
Run: python 01_patient_management.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import (  # noqa: E402
    DEFAULT_BASE_URL,
    CreatePatientRequest,
    ExternalIdentifier,
    ExternalIdentifierMatcher,
    OliraClient,
    OliraEnv,
)

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

# ── Add/remove external identifiers incrementally ────────────────────────────
# update_patient(external_identifiers=...) is merge/append-only: it adds new
# (system, value) pairs and never touches what's already stored. But when you only
# want to attach your own identifier to a patient — without reading and re-sending
# every identifier the patient already has (including ones an EHR integration
# owns) — add_patient_external_identifiers() is the direct way to do it.
mutation = client.add_patient_external_identifiers(
    patient_id=shell.id,
    identifiers=[ExternalIdentifier(system="my-crm", value="CRM-4471")],
)
print(f"Added identifier: added={mutation.added} skipped={mutation.skipped}")

# remove_patient_external_identifiers() is the only way to remove one, and every
# entry is a MATCHER, not just an exact identifier — it removes whatever it matches:
#
#   system + value              -> exactly one identifier (the common case, shown here)
#   system only                 -> every identifier for that system. system="epic"
#                                   unlinks every connected Epic instance — use
#                                   integration_id alone to drop one hospital
#   integration_id only         -> every identifier owned by that specific instance
#   system + integration_id     -> that system on that instance only
#
# It can match ANY identifier — including one owned by a platform integration, which
# is a deliberate, irreversible unlink (the patient stops receiving further data from
# that integration under linked_only import mode). Only remove an integration's
# identifier when you mean to sever that link.
mutation = client.remove_patient_external_identifiers(
    patient_id=shell.id,
    identifiers=[ExternalIdentifierMatcher(system="my-crm", value="CRM-4471")],
)
print(f"Removed one identifier: removed={mutation.removed} skipped={mutation.skipped}")

# System-only matcher: drop every "my-crm" identifier this patient has, whatever
# their values, in one call.
client.add_patient_external_identifiers(
    patient_id=shell.id,
    identifiers=[
        ExternalIdentifier(system="my-crm", value="CRM-1"),
        ExternalIdentifier(system="my-crm", value="CRM-2"),
    ],
)
mutation = client.remove_patient_external_identifiers(
    patient_id=shell.id,
    identifiers=[ExternalIdentifierMatcher(system="my-crm")],
)
print(f"Removed all my-crm identifiers: removed={mutation.removed}")

# integration_id-only matcher: fully unlink a patient from one specific EHR
# integration instance without knowing which system/value it used — useful for
# correcting a bad patient match without a full re-sync.
# mutation = client.remove_patient_external_identifiers(
#     patient_id=shell.id,
#     identifiers=[ExternalIdentifierMatcher(integration_id="<integration-id>")],
# )

# ── Look up by external identifier ───────────────────────────────────────────
# Same filter shapes work for list_patients(): system + value for one exact
# identifier, system alone for every patient with that system, or integration_id
# alone for every patient linked to a specific integration instance.
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

# ── Delete — soft (default) vs. permanent ────────────────────────────────────
# Soft-delete sets status=deleted. The record and all its logs/state are retained
# for audit purposes, and the patient stops appearing in list_patients() — but its
# external identifiers are also freed up, so a new create can reuse the same value.
client.delete_patient(patient_id=shell.id)
print(f"Soft-deleted:   {shell.id} (record + logs retained, hidden from listings)")

# permanent=True hard-deletes the patient AND cascade-deletes every associated
# document (event logs, state, conversations, notes, etc). Irreversible. Use this
# once you're sure a record was created in error (e.g. test data, or a duplicate)
# and you need its logs gone entirely, not just hidden.
client.delete_patient(patient_id=patient.id, permanent=True)
created_ids.remove(patient.id)
print(f"Permanently deleted: {patient.id} (record + all associated data removed)")

# ── Demo cleanup — remove remaining test patients so your org stays clean ────
# Not part of a real integration. permanent=True here so the demo leaves no residue.
for pid in created_ids:
    if pid == shell.id:
        continue  # already soft-deleted above
    client.delete_patient(patient_id=pid, permanent=True)
client.close()
print(f"Cleaned up {len(created_ids)} patients.")
