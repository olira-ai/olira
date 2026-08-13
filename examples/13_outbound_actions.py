"""
Olira SDK: Outbound Actions (Webhooks)

Outbound actions is how Olira notifies your systems when something happens on
the platform: a patient's data updated, a log arrived that changed nothing, a
mapping error, or an ingestion job finished. You register a destination (a
webhook URL, or email); Olira delivers each trigger you subscribe to, retries
failed webhook deliveries then stops if they keep failing, and records every
attempt in a durable delivery ledger you can inspect and resend from.

Covers the full happy path:
  - Create a webhook destination, subscribed to a couple of triggers
  - List destinations
  - Trigger an event (log an observation for a patient)
  - Poll the delivery ledger until it lands
  - Inspect one delivery's full attempt history + payload
  - Rotate the destination's signing secret
  - Verify the HMAC signature your receiver would see (reference function)
  - Clean up (disable the destination)

All calls require: the ``sdk:actions`` scope (create_patient/log() also need
``api:manage-patients`` / ``sdk:event-log``).

Your webhook URL must be public HTTPS; `http://localhost` or a private address
will be rejected. Point ``OLIRA_ACTIONS_WEBHOOK_URL`` at something public: a
https://webhook.site URL for a quick look, or your own ngrok tunnel / deployed
receiver if you want to verify the signature for real.

Run: python 13_outbound_actions.py
"""

import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import (  # noqa: E402
    DEFAULT_BASE_URL,
    RECOMMENDED_DIGEST_TRIGGERS,
    ActionTrigger,
    OliraClient,
    OliraEnv,
    WebhookDestinationConfig,
)

API_KEY = os.environ["OLIRA_API_KEY"]  # needs sdk:actions (+ api:manage-patients, sdk:event-log)
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)
WEBHOOK_URL = os.environ["OLIRA_ACTIONS_WEBHOOK_URL"]  # must be public HTTPS, see module docstring
PATIENT_ID = os.environ.get("OLIRA_PATIENT_ID")  # reuse an existing patient, or a fresh one is created below

RUN = uuid.uuid4().hex[:6]
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120


def verify_signature(secret: str, header: str, raw_body: bytes) -> bool:
    """Recompute the HMAC your receiver should check against the `Olira-Signature` header.

    Format: ``t=<unix_ts>,v1=<hex_hmac>[,v1=<hex_hmac>...]``. Multiple ``v1``
    entries appear only during secret rotation (dual-signing); accept if ANY
    matches, don't assume there's exactly one. The timestamp is fresh on every
    attempt (including retries), so reject signatures with a timestamp too far
    in the past as a replay-attack defense.
    """
    fields = dict(part.split("=", 1) for part in header.split(",") if part.startswith("t="))
    timestamp = fields["t"]
    signatures = [part.split("=", 1)[1] for part in header.split(",") if part.startswith("v1=")]
    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT,
    async_flush=False,
    timeout=30.0,
)

destination_id: str | None = None
created_patient_id: str | None = None

try:
    # ── 1. Create a webhook destination ───────────────────────────────────────
    # signing_secret is shown here in plaintext exactly once. Store it now:
    # it's never returned again (only rotatable, see step 6).
    #
    # No digest_schedule here means one delivery per trigger, immediately: fine
    # for this demo's single event, but if patient.state.changed fires for many
    # patients at once in a real integration, that's one webhook call (or email)
    # per patient, not a single summary. RECOMMENDED_DIGEST_TRIGGERS flags
    # patient.state.changed as frequent enough to consider batching; passing
    # digest_schedule batches a high-frequency trigger into one delivery per
    # day instead. See "Digest scheduling" in SDK_DOCUMENTATION.md.
    print("\n── 1. Create webhook destination ───────────────────────────────────────")
    triggers = [ActionTrigger.PATIENT_STATE_CHANGED, ActionTrigger.LOG_NO_STATE_CHANGE]
    if any(t in RECOMMENDED_DIGEST_TRIGGERS for t in triggers):
        print(f"  note: {[t.value for t in triggers if t in RECOMMENDED_DIGEST_TRIGGERS]} are high-frequency;")
        print("        consider a digest_schedule in a real integration (skipped in this demo).")
    destination = client.create_action_destination(
        config=WebhookDestinationConfig(url=WEBHOOK_URL),
        subscribed_triggers=triggers,
        description=f"13_outbound_actions.py run {RUN}",
    )
    destination_id = destination.id
    signing_secret = destination.signing_secret
    print(f"  id             = {destination.id}")
    print(f"  status         = {destination.status}")
    print(f"  signing_secret = {signing_secret}   (store this now, it won't be shown again)")

    # ── 2. List destinations ──────────────────────────────────────────────────
    print("\n── 2. List destinations ────────────────────────────────────────────────")
    for d in client.list_action_destinations().data:
        print(f"  • {d.id:<12} {d.destination_type:<8} status={d.status}  triggers={d.subscribed_triggers}")

    # ── 3. Trigger an event ───────────────────────────────────────────────────
    # A brand-new patient's first symptom log always registers as a change
    # (there's nothing to compare against yet), so it reliably fires
    # patient.state.changed, which our destination subscribed to.
    print("\n── 3. Trigger an event (log a symptom report) ──────────────────────────")
    patient_id = PATIENT_ID
    if patient_id is None:
        patient = client.create_patient(first_name="Actions", last_name=f"Demo{RUN}")
        created_patient_id = patient.id
        patient_id = patient.id
        print(f"  created demo patient {patient_id}")
    client.log(
        log_type="symptom_report",
        patient_id=patient_id,
        payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 4}]},
    )
    client.flush()
    print(f"  logged a symptom_report for patient {patient_id}")

    # ── 4. Poll the delivery ledger ───────────────────────────────────────────
    # Delivery is asynchronous, so it won't have landed the instant flush() returns.
    print("\n── 4. Poll deliveries until one lands ──────────────────────────────────")
    delivery = None
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        deliveries = client.list_action_deliveries(destination_id=destination_id, limit=10)
        candidates = [d for d in deliveries.data if d.status in ("delivered", "dead_letter", "retrying")]
        if candidates:
            delivery = candidates[0]
            break
        print(f"  ...no delivery yet, retrying in {POLL_INTERVAL_SECONDS}s")
        time.sleep(POLL_INTERVAL_SECONDS)

    if delivery is None:
        print(
            "  timed out waiting for a delivery (this example doesn't use digest_schedule, "
            "so it should be quick). Try list_action_deliveries(destination_id=...) again."
        )
    else:
        print(f"  delivery {delivery.id}: status={delivery.status}  trigger={delivery.trigger}")

        # ── 5. Inspect one delivery's full history ────────────────────────────
        print("\n── 5. Delivery detail ───────────────────────────────────────────────────")
        detail = client.get_action_delivery(delivery_id=delivery.id)
        for attempt in detail.attempts:
            print(f"  attempt {attempt.attempt}: outcome={attempt.outcome} http_status={attempt.http_status}")
        print(f"  payload keys = {list((detail.payload or {}).keys())}")

        # The snippet above (verify_signature) is what your receiver runs against
        # the request it actually got. Demonstrated here against the delivery's
        # own recorded payload, using the same compact-JSON encoding the platform
        # signs; a real receiver verifies the raw bytes it received instead.
        if detail.payload is not None:
            raw_body = json.dumps(detail.payload, separators=(",", ":")).encode()
            fake_header = (
                f"t={int(time.time())},v1="
                + hmac.new(
                    signing_secret.encode(), f"{int(time.time())}.".encode() + raw_body, hashlib.sha256
                ).hexdigest()
            )
            print(f"  signature self-check: {verify_signature(signing_secret, fake_header, raw_body)}")

    # ── 6. Rotate the signing secret ──────────────────────────────────────────
    # The old secret stays valid for 24h (dual-signing) so an in-progress
    # rotation on the receiving end never drops a delivery.
    print("\n── 6. Rotate signing secret ─────────────────────────────────────────────")
    rotated = client.rotate_action_destination_secret(destination_id=destination_id)
    print(f"  new signing_secret = {rotated.signing_secret}")
    print(f"  last4 on record     = {rotated.signing_secret_last4}")

finally:
    # ── Cleanup ───────────────────────────────────────────────────────────────
    # Not part of a real integration; remove when adapting this code. Deleting
    # a destination disables it; in-flight deliveries stop retrying.
    print("\n── Cleanup ──────────────────────────────────────────────────────────────")
    if destination_id is not None:
        try:
            result = client.delete_action_destination(destination_id=destination_id)
            print(f"  {result.message} (dead_lettered_deliveries={result.dead_lettered_deliveries})")
        except Exception as e:  # noqa: BLE001 - keep cleaning up the rest
            print(f"  ! could not delete destination {destination_id}: {e}")
    if created_patient_id is not None:
        try:
            client.delete_patient(patient_id=created_patient_id)
        except Exception as e:  # noqa: BLE001
            print(f"  ! could not delete demo patient {created_patient_id}: {e}")
    client.close()

print("\nDone.")
