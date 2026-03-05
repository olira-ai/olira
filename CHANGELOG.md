# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0a2] - 2026-03-05

### Changed

- **SPEC.md**: API key format corrected from `olira_{hex}` to `olira_{env}_{64-hex-chars}`.
- **SPEC.md**: stale route reference corrected from `routes/mcp/api_keys.py` to `routes/auth/api_keys.py`.
- **SPEC.md**: `EsasItem.symptom_type` field renamed to `type` to match `models.py:129`; `SYMPTOM_DETAIL` payload tables updated to the same field name.
- **SPEC.md**: `POST /v1/patients` create request — removed caller-supplied `id` field; prose updated to "the server assigns a stable `id` at creation time".
- **SPEC.md**: Patient ID Resolution section rewritten — `patient_id` is the Olira-assigned id returned by `create_patient()`, not a caller-supplied identifier; required-fields table and code examples updated accordingly.
- **SPEC.md**: `BatchError` response example — removed phantom `"status"` field; `BatchError` only has `index`, `code`, `message`.
- **SPEC.md**: `UserPatientState` roadmap caveat removed — `create_default_patient_state()` is called at `PatientUser` creation; graph pipeline runs normally.

## [0.1.0a1] - 2026-02-26

### Added

- Initial SDK scaffolding and specification alignment
- Pydantic v2 BaseModel schemas as public API (Option A)
- Package structure: `src/olira/` with hatchling build
