# Olira SDK — Examples

Runnable Python scripts that demonstrate the SDK's main workflows. Each file is self-contained and can be run directly after setup.

## Setup

```bash
cp .env.example .env          # add your OLIRA_API_KEY
uv sync                       # or: pip install -e ".[examples]"
python 00_quickstart.py
```

## Examples

| File | What it shows | Required scope(s) |
|---|---|---|
| `00_quickstart.py` | Create a patient, log one event, flush | `api:manage-patients`, `sdk:event-log` |
| `01_patient_management.py` | Full patient lifecycle: create, shell patient, batch, lookup, update, delete | `api:manage-patients` |
| `02_event_logging.py` | `log()` + `flush()` queue vs `log_batch()`, representative payloads, `OliraTrace` | `sdk:event-log`, `api:manage-patients` |
| `03_fhir_ingestion.py` | `log_fhir()` with Condition, MedicationRequest, Appointment; error handling for unsupported types | `sdk:event-log`, `api:manage-patients` |
| `04_historical_ingestion.py` | Bulk historical load: file upload (Path A) and inline records (Path B), optional `OliraTrace` on logs, two-phase confirm flow | `sdk:historical-ingest` |
| `05_logs_only_workflow.py` | Historical ingestion when patients already exist — logs-only job, no patient records in file | `sdk:historical-ingest`, `api:manage-patients` |
| `06_read_patient_state.py` | Read compiled patient state: stable data, event modules, views, logs, events, memories | `sdk:state-read` |
| `07_patient_token.py` | Mint a patient-scoped JWT, forward to MCP as Bearer, `PatientSession` refresh helper | `sdk:patient-token` |

## Notes

- Examples `04` and `05` both demonstrate historical ingestion; `05` covers the specific case where patients already exist in your org.
- `06_read_patient_state.py` and `07_patient_token.py` require an existing patient id — run `00_quickstart.py` or `02_event_logging.py` first, then pass the printed id or set `PATIENT_ID` in `.env`.
- Cleanup blocks at the end of each script delete demo patients. These are not part of a real integration — remove them when adapting the code.
- Full API reference: [https://olira.ai/api-docs](https://olira.ai/api-docs) (Python SDK tab). Local copy: [`SDK_DOCUMENTATION.md`](../SDK_DOCUMENTATION.md).
