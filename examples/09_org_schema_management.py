"""
Olira SDK — Org Schema/Mapping Management

Covers the self-service registration flow for org-native event subtypes:
  - Register a new subtype (assisted: examples + description only)
  - Dry-run check a candidate schema+mapping before registering it at all
  - Register a second subtype full_spec (schema + mapping already authored)
  - List every subtype you've registered
  - View one subtype's full version history
  - Edit a still-pending request
  - Deprecate (withdraw) a pending request

Registering always lands as a pending request — Olira still reviews and manually
materializes it into a real, versioned type definition + mapping before there is
anything to activate. This example stops short of activation since that requires
Olira to have materialized a version out-of-band first; see docs/org_event_log_schema_mapping_design.md
§6.3 for the full lifecycle including activate_schema_version().

All operations require: api:org-config scope.
Run: python 09_org_schema_management.py
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from olira import DEFAULT_BASE_URL, OliraClient, OliraEnv  # noqa: E402

API_KEY = os.environ["OLIRA_API_KEY"]
BASE_URL = os.environ.get("OLIRA_BASE_URL", DEFAULT_BASE_URL)

client = OliraClient(
    api_key=API_KEY,
    base_url=BASE_URL,
    environment=OliraEnv.DEVELOPMENT,
    async_flush=False,
    timeout=30.0,
)

suffix = uuid.uuid4().hex[:8]
assisted_subtype = f"widget_ping_{suffix}"
full_spec_subtype = f"widget_pong_{suffix}"

# ── 1. Dry-run a candidate schema+mapping before registering anything ────────────
print("\n── 1. Check a candidate schema+mapping (no writes) ─────────────────────")
schema = {"type": "object", "properties": {"note": {"type": "string"}}}
mapping = {
    "source_root": None,
    "targets": [
        {
            "target_subtype": "conversation",
            "field_mappings": [{"target": "channel", "source": "note"}],
        }
    ],
    "unmapped_fields_policy": "drop",
}
examples = [{"note": "hello"}]

check = client.check_schema(schema=schema, mapping=mapping, examples=examples)
print(f"  ok = {check.ok}")
for example_result in check.results:
    print(f"  input={example_result.input}  ok={example_result.ok}  errors={example_result.errors}")
    for event in example_result.mapped_events:
        print(f"    -> {event['subtype']}: {event['payload']}")

# ── 2. Register a new subtype (assisted: Olira authors the schema+mapping) ──────
print(f"\n── 2. Register {assisted_subtype!r} (assisted) ──────────────────────────")
registration = client.register_schema(
    subtype=assisted_subtype,
    description="Example ping event, registered by 09_org_schema_management.py",
    input_examples=examples,
)
print(f"  registration_id  = {registration.registration_id}")
print(f"  submission_mode  = {registration.submission_mode}")
print(f"  status           = {registration.status}")

# ── 3. Register a second subtype full_spec (schema+mapping already authored) ────
print(f"\n── 3. Register {full_spec_subtype!r} (full_spec) ────────────────────────")
full_spec_registration = client.register_schema(
    subtype=full_spec_subtype,
    description="Example pong event, registered by 09_org_schema_management.py",
    input_examples=examples,
    schema=schema,
    mapping=mapping,
)
print(f"  submission_mode  = {full_spec_registration.submission_mode}")
print(f"  self_check.ok    = {full_spec_registration.self_check['ok'] if full_spec_registration.self_check else None}")

# ── 4. List every subtype you've registered ──────────────────────────────────────
print("\n── 4. List schemas ───────────────────────────────────────────────────────")
schemas = client.list_schemas()
print(f"  total registered subtypes: {len(schemas)}")
for summary in schemas:
    if summary.subtype in (assisted_subtype, full_spec_subtype):
        print(f"  • {summary.subtype}  status={summary.status}  active_version={summary.active_version}")

# ── 5. View one subtype's full version history ───────────────────────────────────
print(f"\n── 5. View {assisted_subtype!r} ──────────────────────────────────────────")
detail = client.get_schema(subtype=assisted_subtype)
print(f"  status = {detail.status}")
for version in detail.versions:
    print(f"  • v{version.version}  status={version.status}  source={version.source}")

# ── 6. Edit the still-pending request ────────────────────────────────────────────
print(f"\n── 6. Edit {assisted_subtype!r} ──────────────────────────────────────────")
edited = client.edit_schema(
    subtype=assisted_subtype,
    description="Updated description via edit_schema()",
)
print(f"  target_version  = {edited.target_version}")
print(f"  status          = {edited.status}")

# ── 7. Deprecate (withdraw) both pending requests ────────────────────────────────
print("\n── 7. Deprecate (withdraw) pending requests ─────────────────────────────")
for subtype in (assisted_subtype, full_spec_subtype):
    result = client.deprecate_schema(subtype=subtype)
    print(f"  {subtype}: status={result.status}")

client.close()
print("\nDone.")
