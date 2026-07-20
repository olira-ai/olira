"""
Olira SDK — Quickstart

The shortest path to a working integration:
  1. Initialise the SDK
  2. Create a patient
  3. Log a health event

Requirements: copy .env.example → .env and fill in OLIRA_API_KEY.
Run: python 00_quickstart.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import olira  # noqa: E402
from olira import DEFAULT_BASE_URL, OliraEnv, OliraLogType  # noqa: E402

BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

# Initialise once at startup — all module-level functions (olira.log, olira.create_patient…)
# use this singleton client.
olira.init(
    api_key=os.environ["OLIRA_API_KEY"],
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
    # project="dev-sandbox",  # ← optional: isolate to a project (workspace); or set
    #   OLIRA_PROJECT. Omit for the org's default project. See 10_project_management.py.
)

# 1. Create a patient
patient = olira.create_patient(
    first_name="Jane",
    last_name="Demo",
    date_of_birth="1985-04-12T00:00:00Z",
    timezone="America/New_York",
)
print(f"Patient created: {patient.id}")

# 2. Log a health event — enqueued for background delivery
olira.log(
    log_type=OliraLogType.SYMPTOM_REPORT,
    patient_id=patient.id,
    payload={
        "instrument": "esas_r",
        "symptoms": [{"name": "pain", "score": 3}],
    },
)

# 3. Flush drains the background queue before the process exits.
# In a long-running server, call olira.flush() in your shutdown handler instead
# of inline like this — you don't need to flush after every log() call.
olira.flush()
print("Event delivered.")

# ── Demo cleanup — remove the test patient so your org stays clean ────────────
# Not part of a real integration.
olira.delete_patient(patient_id=patient.id)
print("Done.")
