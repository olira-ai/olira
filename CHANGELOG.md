# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
