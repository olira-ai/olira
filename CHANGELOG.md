# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.10.0] - 2026-07-31

### Added

- **Historical H1 package upload** — `create_ingestion_job(records=…, documents=[IngestDocument(…)])`
  calls `POST /v1/ingestion/jobs:begin`, PUTs each binary (+ `Content-Type`), builds
  `manifest.jsonl` with `type=document` rows, PUTs the manifest, then creates the job with
  `processing_engine="temporal"`. New `IngestDocument` / `IngestRecord.document()`;
  local validation accepts document rows; `IngestionJob` exposes `documents_*` counters.
- **Document upload + OCR** — `OliraClient.upload_document()` / `get_document()`
  (`documents.py`): upload-url → presigned PUT → commit → poll until
  `log_emitted` / `ocr_failed`. Intermediate status `ocr_complete` is non-terminal.
  Caller supplies `log_type` + `document_type` or `note_type`/`source`.
  Requires `sdk:event-log`.
- **`IngestionJobStatus`** — `EXTRACTING` / `LOADING` / `REBASING` /
  `EMBEDDING` match worker `IngestionStage` after historical-ingestion cutover.
- **`IngestionStageWork` / `IngestionJob.stage_work`** — leaf-unit x/N for the active Temporal
  stage (`logs` / `docs` / `blocks`), plus raw ``progress`` on ``IngestionJob``.

### Changed

- **Example `04_historical_ingestion.py`** stage list documents the full pipeline
  (extract → replay → load → rebase → embed → backfill).

### Fixed

- **Presigned document PUT** — send matching `Content-Type` on the S3 PUT (required
  when upload-url signs `ContentType`; without it S3 returns 403).

### Removed

- **`rollback_on_cancel`** on `create_ingestion_job` — cancel cleanup is server-defined (pre-Load
  removes job-created patients with no other history; post-Load is a soft stop).

## [1.9.0] - 2026-07-28

### Added

- **Passive signal ingestion** — `OliraClient.send_signals()` and `get_signal_job()`
  for accelerometer / gyroscope / GPS batches (requires `sdk:event-log` scope).
  - Accepts either `records` (serialized to Parquet locally via optional
    `pip install olira[signals]` / `pyarrow`) or pre-serialized `parquet` bytes.
  - Auto-routes small/medium payloads through the sync door and large payloads via
    presigned S3 + manifest commit; returns a `SignalJobHandle` with `wait()` / `poll()`.
  - Optional collection metadata: `sample_rate_hz`, `units`, `timestamp_unit`,
    `device_timezone`.
  - New models: `SignalJob`, `SignalJobHandle`, `SignalJobStatus`, `SignalSensorType`,
    plus `serialize_signal_records()`.
  - Example: `examples/11_signals.py`.

## [1.8.0] - 2026-07-28

### Added

- `LogEntry.ingested_at` — server ingestion timestamp (distinct from the event's own
  `timestamp`), now returned by `get_logs()` and `.as_logs()`. Matches app-api's
  `ingested_at` exposure in the log query/response layer, so callers can page or filter
  by when an event actually landed on the platform rather than the event's own clock.
- `delete_patient(patient_id, permanent=True)` — hard-delete option, on `OliraClient`,
  `AsyncOliraClient`, and the module-level `delete_patient()`. Soft-delete (sets
  `status=deleted`) remains the default; `permanent=True` cascade-deletes all associated
  data (event logs, state, conversations, etc) via app-api's
  `DELETE /v1/patients/{id}?permanent=true`. Self-serve way to purge a duplicate or
  erroneously-created patient's data without needing Console admin access.

## [1.7.0] - 2026-07-20

### Added

- **Projects — select the workspace your client operates in** (see the platform's
  `docs/projects.md`). Projects are isolated workspaces within an organization
  (separate patients, logs, and configuration).
  - `project` keyword on `OliraClient`, `AsyncOliraClient`, and module-level `init()`
    (also settable via the `OLIRA_PROJECT` environment variable) — selects a project
    by id or slug, sent as the `X-Olira-Project` header on every request. Included in
    the stamped log context alongside `environment`/`service`.
  - New `create_project()`, `list_projects()`, `get_project()`, `duplicate_project()`,
    `rename_project()`, `deprecate_project()`, `restore_project()`, and `delete_project()`
    on both clients and as module-level functions — requires an **org-wide** API key with
    the `api:manage-projects` scope (project-locked keys get 403 on these routes).
  - New `Project` / `ProjectListResult` models.
  - Fully backward compatible: omitting `project` uses a project-locked key's own
    project, or the organization's default project otherwise — existing integrations
    are unaffected.

## [1.6.0] - 2026-07-13

### Added

- **Org schema/mapping management** — `register_schema()`, `list_schemas()`,
  `get_schema()`, `check_schema()`, `edit_schema()`, `deprecate_schema()`, and
  `activate_schema_version()` (sync, async, and module-level), backed by a new
  `api:org-config` scope. Lets orgs register and manage custom event subtypes and
  their payload schema/mapping — `register_schema`/`edit_schema` support both
  "full_spec" (bring your own schema + mapping) and "assisted" (Olira authors them
  from `input_examples` + `description`) submission modes, `check_schema` dry-runs a
  schema/mapping over sample payloads with no writes, and `activate_schema_version`
  re-validates against the type's `sample_payload` before archiving the previously
  active version.

## [1.5.0] - 2026-07-10

### Added

- **EHR write-back from the log APIs** — `log()`, `log_batch()`/`LogSpec` (sync, async,
  and module-level) gain `write_back: bool` and `write_back_integration_id: str | None`.
  `write_back=True` requests that the log also be written into the org's connected EHR
  (a request, not a grant: honored only with the `sdk:integration-write` scope and
  platform-side write configuration — silent no-op otherwise, the log ingests normally).
  With several write-configured integrations of the same type (multi-instance, platform
  2.43.0), `write_back_integration_id` names the target instance.

### Documentation

- New **"EHR Integrations & Instances"** section: multi-instance model (several
  integrations per type, per-instance ids/identifier namespaces), raw
  `/v1/integrations` usage until typed wrappers land, per-instance chart lookup, and
  write-back targeting. `ExternalIdentifier` docs note that SDK-supplied identifiers
  live in their own namespace and never collide with integration-owned ones.

- Added new API docs reference

## [1.4.0] - 2026-07-09

### Added

- **Org-native (custom) event types** — `log()`, `log_batch()`, and `LogSpec.log_type`
  now accept an `OliraLogType | str`, so orgs can emit their own custom/versioned event
  types (e.g. `myorg_custom_event` or `some_type@2`) alongside the platform catalog. The
  backend validates org-native types against the org's schema.

### Changed

- Ingestion validation (`validate_ingestion_file`, `validate_ingestion_records`) no longer
  reports "Unknown event_type" for values that look org-native — those carrying an `@`
  version pin, or containing an underscore and not matching a known platform type. Typos
  that do not look org-native still surface an "Unknown event_type" error with a
  suggestion.
- Ingestion validation rejects non-string `event_type` values with a clear error and
  improves org-native detection so near-miss typos of platform types are not silently
  treated as org-native.

## [1.3.0] - 2026-07-07

### Added

- **`OliraLogType`** — added canonical noun-only members for every log type renamed by the
  platform's OLI-1943 nomenclature change (e.g. `MOOD_REPORT`, `CONVERSATION`, `LAB_RESULTS`,
  `CLINICAL_NOTE`, `CONTENT_INTERACTION`, `TASK_OUTCOME`, `DEMOGRAPHICS`, ...). The platform
  accepts both the new and the old verb-suffixed values indefinitely, so existing deprecated
  members (e.g. `MOODS_REPORT`, `CONVERSATION_COMPLETED`) are unchanged and continue to work;
  new integrations should prefer the canonical member noted in each one's docstring/doc entry.

## [1.2.0] - 2026-06-25

### Added

- **Cohort management** — 10 new methods on `OliraClient`, `AsyncOliraClient`, and module-level
  API (all require `api:manage-patients` scope):
  - `create_cohort(name, description)` → `Cohort`
  - `list_cohorts()` → `CohortListResult`
  - `get_cohort(cohort_id)` → `Cohort`
  - `update_cohort(cohort_id, name, description)` → `Cohort`
  - `delete_cohort(cohort_id)` → `CohortDeleteResult`
  - `add_patients_to_cohort(cohort_id, patient_ids)` → `CohortPatientMutationResult`
  - `remove_patients_from_cohort(cohort_id, patient_ids)` → `CohortPatientMutationResult`
  - `assign_cohort_template(cohort_id, summary_type)` → `CohortTemplateAssignment`
  - `unassign_cohort_template(cohort_id, summary_type)` → `dict`
  - `list_cohort_templates(cohort_id)` → `CohortTemplatesResult`
- New exported models: `Cohort`, `CohortListItem`, `CohortListResult`,
  `CohortPatientMutationResult`, `CohortTemplateAssignment`, `CohortTemplatesResult`,
  `CohortDeleteResult`.
- Example script `examples/08_cohort_management.py` — full cohort lifecycle with patient
  enrolment and template assignment.

## [1.1.0] - 2026-06-08

### Added

- `LogQuery` / `AsyncLogQuery` — fluent, chainable log query builder that compiles to the
  `POST /v1/state/{patient_id}/logs/query` and `POST /v1/state/logs/query` DSL. Entry points: `olira.logs(patient_id)` and
  `olira.population_logs(patient_ids)`.
- Filter operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in_`, `nin`, `like`, `ilike`,
  `is_`, `exists`, `contains` — plus `.or_()` / `.and_()` boolean groups.
- Projection: `.select(*paths, **aliases)`, `.select_array()` for array sub-fields.
- Aggregation: `.group_by()`, `.agg()`, `.count_agg()`, `.sum()`, `.avg()`, `.min()`, `.max()`.
- Modifiers: `.order()`, `.limit()`, `.offset()`, `.range()`.
- Terminals: `.execute() -> LogQueryResult`, `.count() -> int`, `.single()`, `.maybe_single()`.
- `F(field)` expression helper for sub-conditions in `.or_()` / `.and_()`.
- `LogQueryResult` model — iterable, supports `len()` and index access; `.as_logs()` returns
  typed `list[LogEntry]` for no-projection queries.
- Module-level `olira.logs()` / `olira.population_logs()` proxies (singleton-backed, same as
  other module-level helpers).

## [1.0.9] - 2026-06-03

### Added

- `OliraLogType.CARE_ACTION_LOGGED` (`"care_action_logged"`) — log clinical alerts and care tasks.

### Changed

- Event-state module `emotional_state` renamed to `behavioral_state`. New module types `alerts_and_tasks` (event-state) and `treatment_phase` (stable) are now available via `get_event_state_module` / `get_stable_data`.

## [1.0.8] - 2026-05-27

### Changed

- CI: `publish.yml` now triggers on push to `main` — merging automatically creates a `v{version}` git tag, publishes to PyPI, and creates a GitHub Release with auto-generated notes and build artifacts attached.

## [1.0.7] - 2026-05-27

### Fixed

- **`_LogWire.idempotency_key`** (`src/olira/models.py`): Changed from auto-generated UUID to `str | None = None` — callers can now omit the key and let the server handle deduplication semantics rather than silently generating a new key on every call.

## [1.0.6] - 2026-05-26

### Fixed

- **`EventEntry.changes` type** (`src/olira/models.py`): Corrected from `dict[str, Any] | None` to `list[dict[str, Any]] | None` — the API returns an array of change records, not a single dict.
- **`examples/06_read_patient_state.py`**: Updated block traversal to use the current response shape (`template_ref.block_id`, `result.content`).

## [1.0.5] - 2026-05-26

### Added

- `tests/test_models.py`: regression tests for `OliraTrace` / `LogsResult` deserialization with null trace fields and outbound `_LogWire` trace validation.
- `tests/test_validation.py`: ingestion trace wiring and local validation for JSONL / inline records.
- `DEFAULT_BASE_URL` exported from the package — single source of truth for the production API base URL.
- Optional `trace: OliraTrace | None` on `IngestLogSpec` for historical ingestion — same provenance shape as live `log()`; enables `get_logs(trace_type=...)` filtering on backfilled events when both fields are set.

### Fixed

- `get_logs()` no longer raises a Pydantic validation error when a log's `trace` has `object_type` or `object_id` set to `null` (common for historically ingested events).
- Default `base_url` is now `https://app-api.prod.olira.ai/app-api` (was `https://api.prod.olira.ai`, which does not resolve in DNS).

## [1.0.4] - 2026-05-26

### Added

- `IngestionJob.missing_template_slots`: structured map of `patient_id → [missing_summary_type, …]` returned at `AWAITING_CONFIRMATION` when patients lack view slots for org templates (pairs with `error_summary` entries with code `missing_template_slot`).
- `confirm_ingestion_job(..., initialize_missing_templates=False, skip_backfill=False)` on `OliraClient` and `AsyncOliraClient` — pass `initialize_missing_templates=True` to auto-initialize missing view slots before Phase 2 backfill; pass `skip_backfill=True` to skip view generation (PATCH then confirm).
- `patch_ingestion_job(..., skip_backfill=None)` — set `skip_backfill` while the job is in `AWAITING_CONFIRMATION`.

### Changed

- `confirm_ingestion_job` HTTP transport now sends an optional JSON body with `initialize_missing_templates` when set.

### Fixed

- Example `Run:` (and `Usage:`) headers in `03_fhir_ingestion.py`–`06_read_patient_state.py` still referenced pre-reorder filenames after examples were renumbered in 1.0.2.
- `confirm_ingestion_job(..., skip_backfill=True)` is retry-safe: a retried call tolerates HTTP 409 on PATCH or confirm when the job has already left the review gate (including terminal states such as `cancelled` and `failed`), and returns the current job state instead of failing.

## [1.0.3] - 2026-05-22

### Added

- `metadata: dict[str, Any] | None` parameter on `log()`, `LogSpec`, and `_LogWire` — callers can now attach arbitrary key/value context to any event. The metadata is stored server-side as a top-level field, separate from the typed `payload`, and is surfaced in the Olira Console event detail panel.

## [1.0.2] - 2026-05-22

### Added

- `log_fhir(*, patient_id, resource)` on `OliraClient`, `AsyncOliraClient`, and module-level — submits a single FHIR R4 resource for immediate ingestion via `POST /v1/fhir/resource` (`sdk:event-log` scope). Olira maps the resource to one or more platform log types using the same absorber as Epic/Cerner integrations; callers do not choose a `log_type` or build Olira-shaped payloads.
- `ValidationError` is raised when the server returns `accepted=0` (unsupported resource type, unrecognized fields, or missing `resourceType`) — the exception message explains why.
- `examples/03_fhir_ingestion.py`: runnable example covering Condition, MedicationRequest, Appointment, and both error paths.
- `examples/07_patient_token.py`: runnable example covering mint, MCP Bearer forwarding pattern, and a `PatientSession` helper with automatic token refresh.
- Reordered examples: FHIR ingestion moved to `03` (alongside other write paths); historical ingestion `04`–`05`; state read `06`; patient token `07`.

### Changed

- `SDK_DOCUMENTATION.md`: added `log_fhir` method reference under Logs; expanded Patient Token section with when-to-use guidance, token lifetime/refresh notes, and MCP forwarding example.
- `README.md`: added `log_fhir` to the Logging section.

## [1.0.1] - 2026-05-21

### Changed

- README: add `sdk:historical-ingest`, `sdk:state-read`, `mcp:patient-state` scopes; add Historical Ingestion and Patient State sections; rename "Event Logging" → "Logging".
- SDK_DOCUMENTATION.md: update intro description; fix CLI install instructions to Homebrew.
- Bump GitHub Actions to Node.js 24-compatible versions (`actions/checkout@v6`, `actions/setup-python@v6`, `astral-sh/setup-uv@v8.1.0`).
- `check-version.sh`: fix stale monorepo path; add `SDK_DOCUMENTATION.md` version consistency check.

## [1.0.0] - 2026-05-20

First public release of the Olira Python SDK (`pip install olira`).

### Added

- **Event logging** (`sdk:event-log`): `OliraClient.log()`, `log_batch()`, background queue with `flush()`, and module-level `olira.init()` / `olira.log()` / `olira.flush()`.
- **Patient management** (`api:manage-patients`): create, read, update, delete, list, and batch-create patients; `ExternalIdentifier` for linking to EMR or partner IDs.
- **Patient token** (`sdk:patient-token`): `get_patient_token()` for short-lived JWTs used with the [Olira MCP Patient State server](https://docs.olira.ai/mcp-server).
- **Patient state read** (`sdk:state-read`): stable modules, event state modules, views, logs, events, and memories — REST-backed access to compiled patient state from Python.
- **Historical data ingestion** (`sdk:historical-ingest`): JSONL file or inline record upload, two-phase confirm flow, job polling, and local pre-flight validation (`validate_ingestion_file`, `validate_ingestion_records`).
- **Async client**: `AsyncOliraClient` with the same surface as `OliraClient`.
- **Typed models**: `OliraLogType`, payload helpers (`EsasItem`, `LabResultItem`, …), and structured error types (`AuthError`, `ValidationError`, `RateLimitError`, `ServerError`).
- **Examples**: runnable scripts under `examples/` for quickstart, patients, logging, ingestion, and state read.

### Documentation

- API reference: [https://docs.olira.ai/reference/sdk](https://docs.olira.ai/reference/sdk)
- Local reference: `SDK_DOCUMENTATION.md`
