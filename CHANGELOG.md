# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
