"""
Olira SDK — Passive signal ingestion

Upload a tiny accelerometer batch and wait for absorb to finish.

Requirements:
  - copy .env.example → .env and fill in OLIRA_API_KEY (sdk:event-log)
  - pip install olira[signals]  (or: uv sync --extra signals / examples)
Run: python 11_signals.py
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import (  # noqa: E402
    DEFAULT_BASE_URL,  # noqa: E402
    OliraClient,
    OliraEnv,
)

BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

client = OliraClient(
    api_key=os.environ["OLIRA_API_KEY"],
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
)

patient = client.create_patient(
    first_name="Signal",
    last_name="Demo",
    date_of_birth="1990-01-01T00:00:00Z",
    timezone="America/New_York",
)
print(f"Patient created: {patient.id}")

t0 = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
records = [{"ts": t0 + timedelta(milliseconds=i * 50), "x": 0.0, "y": 0.0, "z": 9.81} for i in range(20)]

handle = client.send_signals(
    patient_id=patient.id,
    sensor_type="accelerometer",
    source_device="example-phone-imu",
    sample_rate_hz=20.0,
    records=records,
)
print(f"Job accepted: {handle.job_id}")

job = handle.wait(timeout=120.0)
print(
    f"status={job.status} written={job.records_written} "
    f"deduped={job.records_deduplicated} quarantined={job.records_quarantined}"
)

# ── Demo cleanup ─────────────────────────────────────────────────────────────
client.delete_patient(patient_id=patient.id)
print("Done.")
