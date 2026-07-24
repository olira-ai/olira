"""
Olira SDK — Event Logging

Two logging patterns:
  - log() + flush()   — background queue, best for real-time events
  - log_batch()       — single HTTP call, best for bursts or scripted pipelines

Also covers:
  - Representative payloads for common event types
  - OliraTrace for provenance (linking an event to its originating object)
  - idempotency_key to prevent duplicates on retry

Requires: sdk:event-log scope (logging) + api:manage-patients scope (patient setup)
Run: python 02_event_logging.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import (  # noqa: E402
    DEFAULT_BASE_URL,
    ExternalIdentifier,
    LogSpec,
    OliraClient,
    OliraEnv,
    OliraLogType,
    OliraTrace,
)

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
    # project="dev-sandbox",  # ← select a project (workspace). Logs inherit their
    #   patient's project automatically — you never pass a project when logging;
    #   just target a patient in the workspace you want. Omit for the org default.
    #   See examples/10_project_management.py and SDK_DOCUMENTATION.md#projects.
)

# Setup — create a demo patient
patient = client.create_patient(
    first_name="Logging",
    last_name="Demo",
    timezone="America/New_York",
    external_identifiers=[ExternalIdentifier(system="demo", value="LOG-DEMO-001")],
)
PID = patient.id
print(f"Demo patient: {PID}")

# ── log() + flush() — background queue ───────────────────────────────────────
# Events are enqueued and batched automatically. Call flush() before process exit.
client.log(
    log_type=OliraLogType.USER_LOGIN,
    patient_id=PID,
)

client.log(
    log_type=OliraLogType.SYMPTOM_REPORT,
    patient_id=PID,
    payload={
        "instrument": "esas_r",
        "symptoms": [
            {"name": "pain", "score": 4},
            {"name": "fatigue", "score": 6},
            {"name": "nausea", "score": 2},
        ],
    },
    # Trace links this event back to the conversation that produced it.
    # Useful when an AI agent or a clinical form generates the event.
    trace=OliraTrace(object_type="conversation", object_id="conv-abc-123"),
)

client.flush()
print("Queued events delivered.")

# ── log_batch() — single request, multiple events ────────────────────────────
# Use when you have several events ready at once (e.g. end-of-session sync).
result = client.log_batch(
    [
        LogSpec(
            log_type=OliraLogType.VITALS_MEASUREMENT,
            patient_id=PID,
            payload={
                "measurements": {
                    "systolic_bp_mmhg": 128,
                    "diastolic_bp_mmhg": 82,
                    "heart_rate_bpm": 74,
                },
                "context": {"position": "sitting"},
                "source": "manual_entry",
                "collection_datetime": "2026-01-15T09:00:00Z",
            },
            idempotency_key=f"{PID}:vitals:2026-01-15T09:00:00Z",
        ),
        LogSpec(
            log_type=OliraLogType.MEDICATION_ACTION,
            patient_id=PID,
            payload={
                "medications": [
                    {
                        "action": "add",
                        "medication_name": "Ondansetron 4mg",
                        "dose": "4 mg",
                        "frequency": "every 8h as needed",
                        "route": "oral",
                    }
                ],
            },
            idempotency_key=f"{PID}:med-add:ondansetron-2026-01-15",
        ),
        LogSpec(
            log_type=OliraLogType.LAB_RESULTS_RECEIVED,
            patient_id=PID,
            payload={
                "panel_name": "CBC",
                "collection_datetime": "2026-01-15T08:00:00Z",
                "results": [
                    {
                        "test_name": "Hemoglobin",
                        "value": 10.8,
                        "unit": "g/dL",
                        "reference_range": "12.0–16.0",
                        "status": "low",
                    }
                ],
            },
            idempotency_key=f"{PID}:cbc:2026-01-15",
        ),
        LogSpec(
            log_type=OliraLogType.CONVERSATION_COMPLETED,
            patient_id=PID,
            payload={
                "conversation_id": "conv-abc-123",
                "channel": "chat",
                "transcript": [
                    {"speaker_label": "agent", "text": "How are you feeling today?"},
                    {"speaker_label": "patient", "text": "Still quite fatigued, pain is about a 4."},
                ],
            },
            trace=OliraTrace(object_type="conversation", object_id="conv-abc-123"),
            idempotency_key=f"{PID}:conv:conv-abc-123",
        ),
    ]
)
print(f"log_batch(): accepted={result.accepted}, failed={result.failed}")
if result.errors:
    for err in result.errors:
        print(f"  [{err.index}] {err.code}: {err.message}")

# ── Demo cleanup — remove the test patient so your org stays clean ────────────
# Not part of a real integration.
client.delete_patient(patient_id=PID)
client.close()
print("Done.")
