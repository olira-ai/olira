"""
Olira SDK — EHR Integration Management (raw REST)

Manage EHR integrations programmatically: browse the provider catalog, connect
an instance, watch the async connection probe, subscribe data points, trigger
syncs, and look up a patient's EHR-side id — all without the Console.

Typed Python wrappers are planned; until then these are plain REST calls under
/v1/integrations (this script uses httpx, already a dependency of the SDK).

Multi-instance model: an org may connect SEVERAL integrations of the same type
(e.g. Epic for Hospital A and Hospital B). Every route below keys on the
integration's id — store it. Connecting the SAME provider instance twice
returns 409; different instances of one type coexist. See SDK_DOCUMENTATION.md
§ "EHR Integrations & Instances".

Notes:
  - Connect returns status=pending; a TestConnectionWorkflow probes the
    credentials asynchronously and records connection_status=valid|invalid.
    Activation (pending → active) is an Olira-admin step — data point
    subscription is rejected with 422 until then.
  - This script needs real provider credentials to get past the probe. Set
    EPIC_CLIENT_ID / EPIC_TOKEN_ENDPOINT / EPIC_FHIR_BASE_URL in .env, or run
    it against a sandbox. Without them it stops after the catalog step.

Requires: sdk:integrations scope
Run: python 10_integration_management.py
"""

import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import DEFAULT_BASE_URL  # noqa: E402

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

api = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    timeout=20,
)

# ── 1. Browse the provider catalog ───────────────────────────────────────────
catalog = api.get("/v1/integrations/catalog").json()["data"]
print("Available providers:")
for entry in catalog:
    print(f"  {entry['integration_type']:<10} {entry['name']} ({entry['auth_mode']})")

# ── 2. List existing connections ─────────────────────────────────────────────
integrations = api.get("/v1/integrations").json()["data"]
print(f"\nConnected integrations: {len(integrations)}")
for i in integrations:
    print(
        f"  {i['id']}  {i.get('display_name') or i['integration_type']}  "
        f"status={i['status']} connection={i.get('connection_status')}"
    )

# ── 3. Connect an Epic instance (M2M — three non-secret values) ──────────────
EPIC_CLIENT_ID = os.environ.get("EPIC_CLIENT_ID")
if not EPIC_CLIENT_ID:
    print("\nEPIC_CLIENT_ID not set — stopping after read-only steps.")
    api.close()
    raise SystemExit(0)

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
            "client_id": EPIC_CLIENT_ID,
            "token_endpoint": os.environ["EPIC_TOKEN_ENDPOINT"],
            "api_base_url": os.environ["EPIC_FHIR_BASE_URL"],
        },
    },
)
if resp.status_code == 409:
    # This exact provider instance (same FHIR base URL) is already connected.
    print(f"\nAlready connected: {resp.json()['detail']}")
    api.close()
    raise SystemExit(0)
resp.raise_for_status()
integration = resp.json()["data"]
INTEGRATION_ID = integration["id"]
print(f"\nConnected: {INTEGRATION_ID} ({integration['display_name']}) status={integration['status']}")

# ── 4. Wait for the async connection probe ───────────────────────────────────
for _ in range(12):
    time.sleep(5)
    doc = api.get(f"/v1/integrations/{INTEGRATION_ID}").json()["data"]
    if doc.get("connection_status") in ("valid", "invalid"):
        break
print(
    f"Connection probe: {doc.get('connection_status')}"
    + (f" — {doc.get('error_reason')}" if doc.get("error_reason") else "")
)

# ── 5. Data points (needs Olira-admin activation first) ──────────────────────
# Once the integration is ACTIVE and data points are allowlisted:
dp_catalog = api.get(f"/v1/integrations/{INTEGRATION_ID}/data-points/catalog").json()["data"]
print(f"\nData points available to subscribe: {[d['name'] for d in dp_catalog]}")

sub = api.post(
    f"/v1/integrations/{INTEGRATION_ID}/data-points",
    json={"name": "Patients"},  # roster sync — subscribe this first, always
)
if sub.status_code == 422:
    print(f"Subscribe rejected (integration not active yet): {sub.json()['detail']}")
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

# ── 6. Per-instance patient lookup ───────────────────────────────────────────
# After a Patients sync, resolve an Olira patient's EHR-side id AT THIS instance
# (404 means this instance doesn't know the patient — other instances might):
#   api.get(f"/v1/integrations/{INTEGRATION_ID}/patients/{olira_patient_id}")
#   → {"system": "epic", "external_id": "<FHIR Patient id>", ...}

# ── 7. Rename / update / disconnect ──────────────────────────────────────────
api.patch(f"/v1/integrations/{INTEGRATION_ID}", json={"display_name": "Epic — Hospital A"})
print("\nRenamed instance to 'Epic — Hospital A'")
# Disconnect cascades data point subscriptions and cancels in-flight syncs:
# api.delete(f"/v1/integrations/{INTEGRATION_ID}")

api.close()
