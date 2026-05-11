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
| `03_historical_ingestion.py` | Bulk historical load: file upload (Path A) and inline records (Path B), two-phase confirm flow | `sdk:historical-ingest` |
| `04_logs_only_workflow.py` | Historical ingestion when patients already exist — logs-only job, no patient records in file | `sdk:historical-ingest`, `api:manage-patients` |
| `05_read_patient_state.py` | Read compiled patient state: stable data, event modules, views, logs, events, memories | `sdk:state-read` |

## Notes

- Examples `03` and `04` both demonstrate historical ingestion; `04` covers the specific case where patients already exist in your org.
- Cleanup blocks at the end of each script delete demo patients. These are not part of a real integration — remove them when adapting the code.
- For the full API reference, see [`API_DOCUMENTATION.md`](../API_DOCUMENTATION.md).
