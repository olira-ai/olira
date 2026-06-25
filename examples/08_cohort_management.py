"""
Olira SDK — Cohort Management

Covers the full cohort lifecycle:
  - Create a cohort
  - List cohorts
  - Get cohort detail
  - Update cohort metadata
  - Enrol a patient
  - Assign a summary template
  - List template assignments
  - Unassign a template
  - Remove a patient
  - Delete the cohort

All operations require: api:manage-patients scope.
Run: python 08_cohort_management.py
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import DEFAULT_BASE_URL, OliraClient, OliraEnv  # noqa: E402

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

# Optional: set to a real summary_type slug your org has active (e.g. "symptom_overview").
# If empty, template assignment steps are skipped.
SUMMARY_TYPE = os.environ.get("OLIRA_EXAMPLE_SUMMARY_TYPE", "")

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT,
    async_flush=False,
    timeout=30.0,
)

# ── 1. Create a test patient to enrol ─────────────────────────────────────────
print("\n── 1. Create test patient ──────────────────────────────────────────────")
patient = client.create_patient(
    first_name="Cohort",
    last_name=f"Example{uuid.uuid4().hex[:6]}",
    timezone="America/New_York",
)
print(f"  patient.id = {patient.id}")

# ── 2. Create a cohort ────────────────────────────────────────────────────────
print("\n── 2. Create cohort ────────────────────────────────────────────────────")
cohort = client.create_cohort(
    name=f"Example Cohort {uuid.uuid4().hex[:8]}",
    description="Created by 08_cohort_management.py",
)
print(f"  cohort.id          = {cohort.id}")
print(f"  cohort.name        = {cohort.name}")
print(f"  cohort.patient_ids = {cohort.patient_ids}")

# ── 3. List cohorts ───────────────────────────────────────────────────────────
print("\n── 3. List cohorts ─────────────────────────────────────────────────────")
result = client.list_cohorts()
print(f"  total cohorts in org: {len(result.data)}")
for item in result.data:
    print(f"  • {item.id}  {item.name!r}  patients={item.patient_count}")

# ── 4. Get cohort detail ──────────────────────────────────────────────────────
print("\n── 4. Get cohort ───────────────────────────────────────────────────────")
fetched = client.get_cohort(cohort_id=cohort.id)
print(f"  fetched.name        = {fetched.name}")
print(f"  fetched.description = {fetched.description}")

# ── 5. Update cohort ──────────────────────────────────────────────────────────
print("\n── 5. Update cohort ────────────────────────────────────────────────────")
updated = client.update_cohort(
    cohort_id=cohort.id,
    description="Updated by 08_cohort_management.py",
)
print(f"  updated.description = {updated.description}")

# ── 6. Add patient to cohort ──────────────────────────────────────────────────
print("\n── 6. Add patient to cohort ────────────────────────────────────────────")
add_result = client.add_patients_to_cohort(
    cohort_id=cohort.id,
    patient_ids=[patient.id],
)
print(f"  patient_count after add = {add_result.patient_count}")

# verify via get
detail = client.get_cohort(cohort_id=cohort.id)
print(f"  patient_ids = {detail.patient_ids}")

# ── 7. Template assignment (optional) ─────────────────────────────────────────
if SUMMARY_TYPE:
    print(f"\n── 7. Assign template {SUMMARY_TYPE!r} ─────────────────────────────────")
    assignment = client.assign_cohort_template(
        cohort_id=cohort.id,
        summary_type=SUMMARY_TYPE,
    )
    print(f"  assignment.id           = {assignment.id}")
    print(f"  assignment.summary_type = {assignment.summary_type}")
    print(f"  assignment.template_id  = {assignment.template_id}")

    print("\n── 7b. List cohort templates ───────────────────────────────────────")
    templates = client.list_cohort_templates(cohort_id=cohort.id)
    for t in templates.data:
        print(f"  • {t.summary_type}  assigned_at={t.assigned_at}")

    print(f"\n── 7c. Unassign template {SUMMARY_TYPE!r} ──────────────────────────────")
    unassign_result = client.unassign_cohort_template(
        cohort_id=cohort.id,
        summary_type=SUMMARY_TYPE,
    )
    print(f"  deleted = {unassign_result.get('deleted')}")
else:
    print("\n── 7. Template steps skipped (set OLIRA_EXAMPLE_SUMMARY_TYPE to enable) ──")

# ── 8. Remove patient from cohort ────────────────────────────────────────────
print("\n── 8. Remove patient from cohort ───────────────────────────────────────")
remove_result = client.remove_patients_from_cohort(
    cohort_id=cohort.id,
    patient_ids=[patient.id],
)
print(f"  patient_count after remove = {remove_result.patient_count}")

# ── 9. Delete cohort ──────────────────────────────────────────────────────────
print("\n── 9. Delete cohort ────────────────────────────────────────────────────")
delete_result = client.delete_cohort(cohort_id=cohort.id)
print(f"  deleted    = {delete_result.deleted}")
print(f"  cohort_id  = {delete_result.cohort_id}")

# ── Cleanup ───────────────────────────────────────────────────────────────────
print("\n── Cleanup ─────────────────────────────────────────────────────────────")
client.delete_patient(patient_id=patient.id)
print(f"  Soft-deleted patient {patient.id}")

client.close()
print("\nDone.")
