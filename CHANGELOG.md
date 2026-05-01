# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0a9] - 2026-05-01

### Changed

- **Logging API (breaking):** Rename `OliraEventType` → **`OliraLogType`** (`OliraEventType` remains as a deprecated alias). Use **`log_type=`** on `log()` / `AsyncOliraClient.log()` and on **`LogSpec`** (was `event_type`). **`get_logs`** filter argument is **`log_types=`** (still serialized to the REST query parameter `event_types`).
- **Patient State — Read (breaking):** Align SDK method and model names with MCP / REST **views**, **logs**, and **events** terminology:
  - `list_summaries` → `list_views`, `list_summary_blocks` → `list_view_blocks`, `get_summary` → `get_view`, `get_summary_block` → `get_view_block`, `get_summary_recent_events` → `get_view_recent_events`
  - `get_event_logs` → `get_logs`, `get_state_transitions` → `get_events` (parameter `event_log_type` → `log_type`; response fields `event_logs` → `logs`, `state_transitions` → `events`; transition fields `event_log_type` → `log_type`, `event_log_payload` → `log_payload`)
  - Models: `SummaryMeta` → `ViewMeta`, `SummaryResult` → `ViewResult`, etc.
- **Log wire JSON** (`LogWire`, HTTP transport): Batch requests send **`{"logs": [...]}`** only. Each entry uses **`log_type`** and **`log_id`** (replacing `events` / `event_name` / `event_id`). Direct HTTP clients must use the new keys.

## [0.1.0a8] - 2026-04-29

### Added

- **Patient State — Read** (`sdk:state-read` scope): 11 new methods on `OliraClient` and `AsyncOliraClient` for reading compiled patient state directly from Python without calling the MCP JSON-RPC interface:
  - `get_stable_data(patient_id, modules=None)` — demographics, condition/diagnosis, medications, preferences
  - `list_event_state_modules(patient_id)` — list active event state module types
  - `get_event_state_module(patient_id, module_type)` — symptoms, emotional state, adherence, activity, engagement
  - `list_summaries(patient_id)` — list available summary types with segment availability flags
  - `list_summary_blocks(patient_id, summary_type)` — list blocks within a summary (week / long_term)
  - `get_summary(patient_id, summary_type, segment="week")` — compiled AI summary snapshot
  - `get_summary_block(patient_id, summary_type, block_id, segment="week")` — single block with confidence scores
  - `get_summary_recent_events(patient_id, summary_type, limit=50)` — live TEMP segment entries
  - `get_event_logs(patient_id, since=None, limit=50, event_types=None, trace_type=None, trace_id=None)` — event log with optional trace, type, and time filtering
  - `get_state_transitions(patient_id, ...)` — events driven by logs, with trace-based resolution
  - `read_memories(patient_id, query=None, limit=100)` — patient memories with optional text search
- **16 new response models** exported from `olira`: `StableDataResult`, `StableModule`, `EventStateModuleSummary`, `EventStateModuleResult`, `SummaryMeta`, `SummaryBlockMeta`, `SummaryBlocksListResult`, `SummaryResult`, `SummaryBlockResult`, `SummaryRecentEventsResult`, `EventLogEntry`, `EventLogsResult`, `StateTransitionEntry`, `StateTransitionsResult`, `MemoryEntry`, `MemoriesResult`.
- All 11 methods available as module-level proxy functions on the singleton (`olira.get_event_logs(...)` etc.).

## [0.1.0a7] - 2026-04-17

### Added

- **8 new event types** synced from the platform event catalog: `PROCEDURE_PERFORMED`, `CARE_GOAL_REPORTED`, `IMMUNIZATION_REPORTED`, `ALLERGY_INTOLERANCE_REPORTED`, `FAMILY_HISTORY_REPORTED`, `DEVICE_REPORTED`, `MEMORY_REPORT`, `UNSTRUCTURED_REPORT_RECEIVED` (already present — no change).

### Changed

- **`CONDITION_UPDATED`** renamed to **`CONDITION_RECORDED`** to match the platform event catalog. Update any `OliraEventType.CONDITION_UPDATED` references to `OliraLogType.CONDITION_RECORDED` (or `OliraEventType.CONDITION_RECORDED`).

## [0.1.0a6] - 2026-04-07

### Removed

- **`get_events()`** and **`delete_events()`** removed from `OliraClient`, `AsyncOliraClient`, and the module-level singleton. The `sdk:event-management` scope has been retired and is no longer issued.
- **`EventSpec`** renamed to **`LogSpec`** — update all `from olira import EventSpec` imports to `from olira import LogSpec`. `EventSpec` is no longer exported.
- **`EventRecord`**, **`EventQueryResult`**, **`DeleteResult`** models removed from the public API and from `olira.__all__`.
- **`sdk:event-management`** scope removed — API keys with this scope will no longer be accepted. Existing keys should be rotated; the scope flag is ignored server-side.

### Changed

- **Log batch route** renamed from `POST /v1/events/batch` to **`POST /v1/logs/batch`**. The old path returns `404`. Update any direct HTTP integrations accordingly.
- **Route file** renamed from `routes/sdk/events.py` to `routes/sdk/logs.py` (internal; no customer-facing impact beyond the URL change above).
- **Single-event endpoint removed** — `POST /v1/events` (single-event ingestion) is no longer available. All log ingestion goes through `POST /v1/logs/batch`. The SDK's `log()` method continues to work unchanged — it batches internally and calls the batch endpoint.
- **SPEC.md**, **README.md**, **CHANGELOG.md** updated to reflect the above changes.

## [0.1.0a5] - 2026-03-19

### Changed

- **`API_DOCUMENTATION.md`**: Updated SDK reference documentation with latest API surface, examples, and error-handling guidance.

## [0.1.0a4] - 2026-03-16

### Fixed

- **SPEC.md**: `medication_action` `action` field enum corrected from `'added'|'updated'|'deleted'` to `'add'|'update'|'delete'` in section 5.6 (table and example payload) and appendix A.6 (table, notes column, and footer prose). The authoritative values have always been `"add"`, `"update"`, `"delete"` — this was a documentation-only regression introduced in the previous session.

### Changed

- **API_DOCUMENTATION.md**: Added **Getting Started** section at the top — covers `pip install olira`, `olira.init()`, `create_patient()`, `olira.log()`, and `olira.flush()` as a copy-paste runnable quickstart.
- **API_DOCUMENTATION.md**: Fixed factual error in "Create a patient" — the description now correctly states that Olira assigns the patient `id` at creation time rather than the caller supplying it.
- **API_DOCUMENTATION.md**: Added **module-level singleton example** (`olira.init()` / `olira.log()` / `olira.flush()`) alongside the existing `OliraClient` example in the "Log a single event" section.
- **API_DOCUMENTATION.md**: Fixed stale `GET /v1/events` response example — added `"instrument": "esas_r"` to the `symptom_report` payload and removed the stale `"total_score"` field.
- **API_DOCUMENTATION.md**: Added **Error Handling** section — documents the typed exception hierarchy (`AuthError`, `ValidationError`, `RateLimitError`, `ServerError`) with a try/except example and a reference table.
- **API_DOCUMENTATION.md**: Added **Common Event Payloads** section — copy-paste examples for `symptom_report`, `lab_results_received`, `medication_action`, and `conversation_completed`.

## [0.1.0a3] - 2026-03-09

### Added

- **`create_patients_batch(patients)`** on `OliraClient` and `AsyncOliraClient`: batch-create up to 500 patients in a single `POST /v1/patients/batch` call. Returns a `PatientBatchResult` with `count` (total submitted), `items` (successes, each with `index`, `id`, `source`), and `errors` (failures, each with `index`, `code`, `message`). Partial success is supported — a failure for one patient does not abort the rest.
- **`PatientBatchItem`** model: represents a successfully created patient in a batch response (`index`, `id`, `source`).
- **`PatientBatchResult`** model: top-level batch response (`count`, `items: list[PatientBatchItem]`, `errors: list[BatchError]`).
- Both new models are exported from the top-level `olira` package and included in `__all__`.
- Module-level `olira.create_patients_batch()` proxy function for singleton-client users.
- `POST /v1/patients/batch` documented in `API_DOCUMENTATION.md` under the Patients section.

## [0.1.0a2] - 2026-03-05

### Changed

- **SPEC.md**: API key format corrected from `olira_{hex}` to `olira_{env}_{64-hex-chars}`.
- **SPEC.md**: stale route reference corrected from `routes/mcp/api_keys.py` to `routes/auth/api_keys.py`.
- **SPEC.md**: `EsasItem.symptom_type` field renamed to `type` to match `models.py:129`; `SYMPTOM_DETAIL` payload tables updated to the same field name.
- **SPEC.md**: `POST /v1/patients` create request — removed caller-supplied `id` field; prose updated to "the server assigns a stable `id` at creation time".
- **SPEC.md**: Patient ID Resolution section rewritten — `patient_id` is the Olira-assigned id returned by `create_patient()`, not a caller-supplied identifier; required-fields table and code examples updated accordingly.
- **SPEC.md**: `BatchError` response example — removed phantom `"status"` field; `BatchError` only has `index`, `code`, `message`.
- **SPEC.md**: `UserPatientState` roadmap caveat removed — `create_default_patient_state()` is called at `PatientUser` creation; graph pipeline runs normally.

---

## [0.1.0a1] - 2026-02-26

### Added

- Initial SDK scaffolding and specification alignment
- Pydantic v2 BaseModel schemas as public API (Option A)
- Package structure: `src/olira/` with hatchling build
