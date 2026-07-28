"""
Olira SDK — Read Patient State

After patients have data (logged via log_batch or ingested via create_ingestion_job),
the state-read methods give you direct access to the compiled patient state:

  get_stable_data()           — demographics, conditions, medications, preferences
  get_event_state_module()    — rolling event state (symptoms, moods, vitals, labs…)
  list_views() / get_view()   — materialised summary snapshots (the "views" clinicians see)
  get_logs()                  — raw event log with optional filters
  get_events()                — state transitions driven by those logs
  read_memories()             — clinical memories extracted from conversations

These are a REST mirror of the MCP Patient State tools — useful for backends and
pipelines that don't go through the MCP server.

Requires: sdk:state-read scope
Run: python 06_read_patient_state.py

Note: this script expects a patient with existing data. Set PATIENT_ID in .env
or supply it as the first CLI argument.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import DEFAULT_BASE_URL, OliraClient, OliraEnv  # noqa: E402

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)
PATIENT_ID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PATIENT_ID", "")

if not PATIENT_ID:
    print("Usage: python 06_read_patient_state.py <patient_id>")
    print("  Or set PATIENT_ID in your .env file.")
    raise SystemExit(1)

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT if "localhost" in BASE_URL else OliraEnv.PRODUCTION,
    async_flush=False,  # state-read uses direct HTTP calls, not the background log queue
)

print(f"Reading state for patient {PATIENT_ID}\n")

# ── Stable data — demographics, condition, medications ────────────────────────
print("── Stable data ──")
stable = client.get_stable_data(patient_id=PATIENT_ID)
for module_type, module in stable.modules.items():
    print(f"  {module_type}: {str(module.payload)[:120]}")

# ── Event state modules — rolling clinical state ──────────────────────────────
print("\n── Event state modules ──")
module_summaries = client.list_event_state_modules(patient_id=PATIENT_ID)
print(f"  Present modules: {[m.module_type for m in module_summaries]}")

# Fetch a specific module in full — adjust module_type to one that's present
for preferred in ("symptoms", "behavioral_state", "lab_results", "vitals"):
    if any(m.module_type == preferred for m in module_summaries):
        module = client.get_event_state_module(patient_id=PATIENT_ID, module_type=preferred)
        print(f"\n  {preferred} module:")
        payload_str = str(module.payload)
        print(f"    {payload_str[:300]}{'…' if len(payload_str) > 300 else ''}")
        break

# ── Views — materialised summary snapshots ─────────────────────────────────────
print("\n── Views ──")
views = client.list_views(patient_id=PATIENT_ID)
print(f"  Available: {[(v.view_type, 'has_blocks=' + str(v.has_blocks)) for v in views]}")

# Fetch the first view that has content
for view_meta in views:
    if view_meta.has_blocks or getattr(view_meta, "has_temp", False):
        view = client.get_view(patient_id=PATIENT_ID, view_type=view_meta.view_type)
        print(f"\n  {view_meta.view_type}:")
        blocks = view.content.get("blocks", [])
        for block in blocks[:2]:
            tr = block.get("template_ref") or {}
            result_d = block.get("result") or {}
            name = tr.get("block_id") or result_d.get("id") or result_d.get("name") or "?"
            text = str(result_d.get("content") or result_d.get("name") or "")[:200]
            print(f"    [{name}] {text}")
        temp = view.content.get("temp", [])
        if temp:
            print(f"    TEMP entries: {temp[:3]}")
        break

# ── Recent logs ────────────────────────────────────────────────────────────────
print("\n── Recent logs (last 5) ──")
logs = client.get_logs(patient_id=PATIENT_ID, limit=5)
print(f"  Total logs on record: {logs.count}")
for entry in logs.logs:
    # timestamp: when the event happened. ingested_at: when the platform received it —
    # these can differ for backfilled or delayed-sync events.
    print(
        f"  timestamp={entry.timestamp or '?'}  ingested_at={entry.ingested_at or '?'}  "
        f"{entry.type}  payload keys: {list((entry.payload or {}).keys())}"
    )

# ── State events ───────────────────────────────────────────────────────────────
print("\n── Recent state events (last 5) ──")
events = client.get_events(patient_id=PATIENT_ID, limit=5)
print(f"  Total events: {events.count}")
for evt in events.events:
    print(f"  {evt.triggered_at or '?'}  {evt.log_type}  status={evt.status}")

# ── Memories ───────────────────────────────────────────────────────────────────
print("\n── Memories (first 5) ──")
memories = client.read_memories(patient_id=PATIENT_ID, limit=5)
print(f"  Total memories: {memories.count}")
for mem in memories.results:
    print(f"  [{mem.memory_id}] {mem.content[:120]}")

client.close()
