"""
Olira SDK — EHR Integrations

Olira connects to a growing pool of EHR and clinical-data providers — Epic,
Healthie, Vivlio, and more (browse them with GET /v1/integrations/catalog).
Every provider follows the same pattern shown here: connect → probe →
subscribe data points → sync → write back. This walkthrough focuses on Epic;
swap the integration_type and credential fields for any other provider.

  A. Manage integrations via the /v1/integrations REST routes — browse the
     catalog, connect an instance, watch the connection check, subscribe
     data points, trigger syncs, look up a patient's EHR-side id, rename.
  B. Write back into the EHR from the log APIs — write_back=True on log() and
     LogSpec/log_batch(), with write_back_integration_id targeting a specific
     instance.

Typed Python wrappers for the management routes are planned; until then they
are plain REST calls (this script uses httpx, already a dependency of the SDK).

Multiple instances of one provider: your organization can connect SEVERAL
integrations of the same type (e.g. Epic for Hospital A and Hospital B).
Every management route keys on the integration's id — store it. Connecting
the SAME provider instance twice returns 409; different instances of one type
coexist. See SDK_DOCUMENTATION.md § "EHR Integrations & Instances".

Data point availability depends on YOUR connected app: for Epic, the data
points you can subscribe to are determined by the Epic app registered for
your health system (its approved scopes/tier) — the data-point catalog
endpoint already reflects what your integration is entitled to. Other
providers gate availability the same way through their own credentials.

Write-back is a REQUEST, not a grant. The write fires only when:
  1. your API key carries the sdk:integration-write scope, AND
  2. Olira has write-configured the integration for the log type
     (a per-health-system enablement — contact Olira to set it up).
Otherwise it is a silent no-op — the log still ingests into Olira normally,
and the API response is identical either way. Target selection without an
explicit id: single write-configured integration → inferred; several → the
patient's integration-linked identifiers decide; ambiguous → no write
(never a guess).

Notes:
  - Connect returns status=pending; Olira verifies the credentials
    asynchronously and records connection_status=valid|invalid. Activation
    (pending → active) is completed by Olira during onboarding — data point
    subscription is rejected with 422 until then.
  - Part A needs real provider credentials to get past the connection check.
    Set EPIC_CLIENT_ID / EPIC_TOKEN_ENDPOINT / EPIC_FHIR_BASE_URL in .env, or
    run against a sandbox. Without them the script skips ahead to Part B.

Requires: sdk:integrations (management) + sdk:event-log & sdk:integration-write
          (write-back) + api:manage-patients (patient setup)
Run: python 09_ehr_integrations.py
"""

import os
import time
from pathlib import Path

import httpx
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
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

api = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    timeout=20,
)

# ═════════════════════════════════════════════════════════════════════════════
# Part A — Integration management (raw REST, sdk:integrations scope)
# ═════════════════════════════════════════════════════════════════════════════

# ── A1. Browse the provider catalog ──────────────────────────────────────────
catalog = api.get("/v1/integrations/catalog").json()["data"]
print("Available providers:")
for entry in catalog:
    print(f"  {entry['integration_type']:<10} {entry['name']} ({entry['auth_mode']})")

# ── A2. List existing connections ────────────────────────────────────────────
integrations = api.get("/v1/integrations").json()["data"]
print(f"\nConnected integrations: {len(integrations)}")
for i in integrations:
    print(
        f"  {i['id']}  {i.get('display_name') or i['integration_type']}  "
        f"status={i['status']} connection={i.get('connection_status')}"
    )

# ── A3. Connect an Epic instance (M2M — three non-secret values) ─────────────
INTEGRATION_ID: str | None = None
EPIC_ENV_VARS = ("EPIC_CLIENT_ID", "EPIC_TOKEN_ENDPOINT", "EPIC_FHIR_BASE_URL")
missing = [name for name in EPIC_ENV_VARS if not os.environ.get(name)]
if missing:
    print(f"\n{', '.join(missing)} not set — skipping connect/subscribe, jumping to write-back.")
else:
    resp = api.post(
        "/v1/integrations",
        json={
            "integration_type": "epic",
            # Cosmetic instance label — distinguishes this connection from other
            # Epic instances your org may add later. Renameable via PATCH.
            "display_name": "Epic — Example Hospital",
            "auth_mode": "m2m",
            "credentials": {
                "type": "m2m_jwt",
                "client_id": os.environ["EPIC_CLIENT_ID"],
                "token_endpoint": os.environ["EPIC_TOKEN_ENDPOINT"],
                "api_base_url": os.environ["EPIC_FHIR_BASE_URL"],
            },
        },
    )
    if resp.status_code == 409:
        # This exact provider instance (same FHIR base URL) is already connected.
        print(f"\nAlready connected: {resp.json()['detail']}")
    else:
        resp.raise_for_status()
        integration = resp.json()["data"]
        INTEGRATION_ID = integration["id"]
        print(f"\nConnected: {INTEGRATION_ID} ({integration['display_name']}) status={integration['status']}")

        # ── A4. Wait for the async connection probe ──────────────────────────
        doc = integration
        for _ in range(12):
            time.sleep(5)
            doc = api.get(f"/v1/integrations/{INTEGRATION_ID}").json()["data"]
            if doc.get("connection_status") in ("valid", "invalid"):
                break
        print(
            f"Connection probe: {doc.get('connection_status')}"
            + (f" — {doc.get('error_reason')}" if doc.get("error_reason") else "")
        )

        # ── A5. Data points ───────────────────────────────────────────────────
        # The catalog below reflects what YOUR connected Epic app is entitled
        # to (its approved scopes/tier) — other orgs may see a different list.
        dp_catalog = api.get(f"/v1/integrations/{INTEGRATION_ID}/data-points/catalog").json()["data"]
        print(f"\nData points available to your Epic app: {[d['name'] for d in dp_catalog]}")

        sub = api.post(
            f"/v1/integrations/{INTEGRATION_ID}/data-points",
            json={"name": "Patients"},  # roster sync — subscribe this first, always
        )
        if sub.status_code == 422:
            print(f"Subscribe rejected (Olira has not activated the integration yet): {sub.json()['detail']}")
        else:
            sub.raise_for_status()
            dp = sub.json()["data"]
            print(f"Subscribed: {dp['name']} ({dp['id']})")

            # Trigger an immediate sync instead of waiting for the scheduler tick.
            sync = api.post(f"/v1/integrations/{INTEGRATION_ID}/data-points/{dp['id']}/sync")
            print(
                f"Sync now → {sync.status_code} "
                f"({sync.json().get('workflow_id') if sync.status_code == 202 else sync.json().get('detail')})"
            )

            # Poll subscription status / last sync summary.
            time.sleep(10)
            points = api.get(f"/v1/integrations/{INTEGRATION_ID}/data-points").json()["data"]
            for p in points:
                print(f"  {p['name']}: status={p['status']} summary={p.get('last_sync_summary')}")

        # ── A6. Per-instance patient lookup ───────────────────────────────────
        # After a Patients sync, resolve an Olira patient's EHR-side id AT THIS
        # instance (404 = this instance doesn't know the patient; others might):
        #   api.get(f"/v1/integrations/{INTEGRATION_ID}/patients/{olira_patient_id}")
        #   → {"system": "epic", "external_id": "<FHIR Patient id>", ...}

        # ── A7. Rename (PATCH also updates credentials / endpoint) ───────────
        api.patch(f"/v1/integrations/{INTEGRATION_ID}", json={"display_name": "Epic — Hospital A"})
        print("Renamed instance to 'Epic — Hospital A'")
        # Disconnect cascades data points and cancels in-flight syncs:
        # api.delete(f"/v1/integrations/{INTEGRATION_ID}")

# ═════════════════════════════════════════════════════════════════════════════
# Part B — Write-back from the log APIs (sdk:event-log + sdk:integration-write)
# ═════════════════════════════════════════════════════════════════════════════

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
)

# In real use, write-back targets patients the EHR knows: synced from its
# roster (Part A) or chart-linked via Patient.Create write-back.
patient = client.create_patient(first_name="Writeback", last_name="Demo", timezone="UTC")
PID = patient.id
print(f"\nDemo patient: {PID}")

# ── B1. write_back on log() — background queue ───────────────────────────────
# The vitals reading ingests into Olira normally AND is requested for
# write-back into the EHR (composed by the platform as a FHIR Observation).
client.log(
    log_type=OliraLogType.VITALS_MEASUREMENT,
    patient_id=PID,
    payload={
        "measurements": {"weight_kg": 72.5, "systolic_bp_mmhg": 118, "diastolic_bp_mmhg": 76},
        "collection_datetime": "2026-07-10T08:00:00Z",
    },
    write_back=True,
    # None → platform infers the target (single write-configured integration,
    # else the patient's instance-linked identifiers). Pass the id explicitly
    # when several instances of the same type are write-configured.
    write_back_integration_id=INTEGRATION_ID,
)
client.flush()
print("Queued vitals log with write_back=True")

# ── B2. write_back on log_batch() — per-event control ────────────────────────
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
api.close()
