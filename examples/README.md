# Olira SDK — Examples

Runnable Python scripts (and one Jupyter notebook) that demonstrate the SDK's main workflows. Each file is self-contained and can be run directly after setup.

## Setup

```bash
cp .env.example .env          # add your OLIRA_API_KEY
uv sync                       # or: pip install -e ".[examples]"
python 00_quickstart.py
```

## Examples

| File                         | What it shows                                                                                                                                                                                                                                                                 | Required scope(s)                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `00_quickstart.py`           | Create a patient, log one event, flush                                                                                                                                                                                                                                        | `api:manage-patients`, `sdk:event-log`                                              |
| `01_patient_management.py`   | Full patient lifecycle: create, shell patient, batch, lookup, update, delete                                                                                                                                                                                                  | `api:manage-patients`                                                               |
| `02_event_logging.py`        | `log()` + `flush()` queue vs `log_batch()`, representative payloads, `OliraTrace`                                                                                                                                                                                             | `sdk:event-log`, `api:manage-patients`                                              |
| `03_fhir_ingestion.py`       | `log_fhir()` with Condition, MedicationRequest, Appointment; error handling for unsupported types                                                                                                                                                                             | `sdk:event-log`, `api:manage-patients`                                              |
| `04_historical_ingestion.py` | Bulk historical load: file upload (Path A) and inline records (Path B), optional `OliraTrace` on logs, two-phase confirm flow                                                                                                                                                 | `sdk:historical-ingest`                                                             |
| `05_logs_only_workflow.py`   | Historical ingestion when patients already exist — logs-only job, no patient records in file                                                                                                                                                                                  | `sdk:historical-ingest`, `api:manage-patients`                                      |
| `06_read_patient_state.py`   | Read compiled patient state: stable data, event modules, views, logs, events, memories                                                                                                                                                                                        | `sdk:state-read`                                                                    |
| `07_patient_token.py`        | Mint a patient-scoped JWT, forward to MCP as Bearer, `PatientSession` refresh helper                                                                                                                                                                                          | `sdk:patient-token`                                                                 |
| `08_cohort_management.py`    | Full cohort lifecycle: create, list, get, update, enrol patients, assign/unassign templates, delete                                                                                                                                                                           | `api:manage-patients`                                                               |
| `09_ehr_integrations.py`     | EHR integrations end-to-end: management via raw REST (catalog, connect an instance, probe polling, data points + sync-now, per-instance patient lookup, rename) and write-back from `log()`/`log_batch()` (`write_back`, `write_back_integration_id` for multi-instance orgs) | `sdk:integrations`, `sdk:event-log`, `sdk:integration-write`, `api:manage-patients` |
| `10_project_management.py`   | Full project (workspace) lifecycle: list, create, select via `OliraClient(project=...)`, duplicate (config-only), rename, deprecate, restore, permanent delete                                                                                                                | `api:manage-projects` (org-wide key), `api:manage-patients`                         |
| `11_signals.py`              | Passive accelerometer Parquet via `OliraClient.send_signals`, wait for absorb                                                                                                                                                                                                   | `sdk:event-log`, `api:manage-patients` (+ `pip install olira[signals]`)             |
| `12_document_resource_ingestion.ipynb` | Document resource ingestion: live `upload_document()` / OCR poll, plus historical `create_ingestion_job(documents=[IngestDocument(…)])` package path                                                                                                                      | `sdk:event-log`, `sdk:historical-ingest`, `api:manage-patients`                     |

## Working with projects

A **project** is an isolated workspace within your org (its own patients, logs, state, views, cohorts, config). To operate _inside_ a project, select it at init — every data call in the other examples then reads/writes within that workspace:

```python
# module-level
olira.init(api_key=API_KEY, project="dev-sandbox")   # or set OLIRA_PROJECT

# or with the client class
client = OliraClient(api_key=API_KEY, project="dev-sandbox")
```

Omit `project` and a project-locked key uses its own project, while an org-wide key uses the org's **default** project (the pre-projects behavior). To manage the projects themselves (create/duplicate/rename/deprecate/restore/delete), see `10_project_management.py` — those calls need an org-wide key with `api:manage-projects`.

## Notes

- Examples `04` and `05` both demonstrate historical ingestion; `05` covers the specific case where patients already exist in your org.
- `12_document_resource_ingestion.ipynb` is a Jupyter notebook (`uv sync` installs `ipykernel`). Set `DOCUMENT_PATH` in `.env` to a real PDF/image for end-to-end OCR; otherwise the notebook writes a tiny stub PDF (upload works; OCR may fail on the stub).
- `10_project_management.py` needs an **org-wide** key with `api:manage-projects` (a project-locked key is confined to its own workspace); it creates, duplicates, and deletes throwaway projects and cleans them up.
- `06_read_patient_state.py` and `07_patient_token.py` require an existing patient id — run `00_quickstart.py` or `02_event_logging.py` first, then pass the printed id or set `PATIENT_ID` in `.env`.
- `08_cohort_management.py` includes template assignment steps that are skipped by default. Set `OLIRA_EXAMPLE_SUMMARY_TYPE` in `.env` (e.g. `symptom_snapshot`) to a summary type active in your org to run them.
- Cleanup blocks at the end of each script delete demo patients. These are not part of a real integration — remove them when adapting the code.
- Full API reference: [https://docs.olira.ai/reference/sdk](https://docs.olira.ai/reference/sdk). Local copy: [`SDK_DOCUMENTATION.md`](../SDK_DOCUMENTATION.md).
