# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.2] - 2026-05-22

### Added

- `log_fhir(*, patient_id, resource)` on `OliraClient`, `AsyncOliraClient`, and module-level — submits a single FHIR R4 resource for immediate ingestion via `POST /v1/fhir/resource` (`sdk:event-log` scope). Olira maps the resource to one or more platform log types using the same absorber as Epic/Cerner integrations; callers do not choose a `log_type` or build Olira-shaped payloads.
- `ValidationError` is raised when the server returns `accepted=0` (unsupported resource type, unrecognized fields, or missing `resourceType`) — the exception message explains why.
- `examples/06_fhir_ingestion.py`: runnable example covering Condition, MedicationRequest, Appointment, and both error paths.
- `examples/07_patient_token.py`: runnable example covering mint, MCP Bearer forwarding pattern, and a `PatientSession` helper with automatic token refresh.

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
- **Patient token** (`sdk:patient-token`): `get_patient_token()` for short-lived JWTs used with the [Olira MCP Patient State server](https://olira.ai/api-docs).
- **Patient state read** (`sdk:state-read`): stable modules, event state modules, views, logs, events, and memories — REST-backed access to compiled patient state from Python.
- **Historical data ingestion** (`sdk:historical-ingest`): JSONL file or inline record upload, two-phase confirm flow, job polling, and local pre-flight validation (`validate_ingestion_file`, `validate_ingestion_records`).
- **Async client**: `AsyncOliraClient` with the same surface as `OliraClient`.
- **Typed models**: `OliraLogType`, payload helpers (`EsasItem`, `LabResultItem`, …), and structured error types (`AuthError`, `ValidationError`, `RateLimitError`, `ServerError`).
- **Examples**: runnable scripts under `examples/` for quickstart, patients, logging, ingestion, and state read.

### Documentation

- API reference: [https://olira.ai/api-docs](https://olira.ai/api-docs) (Python SDK tab)
- Local reference: `SDK_DOCUMENTATION.md`
