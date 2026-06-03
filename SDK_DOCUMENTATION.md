> **Maintained by:** Olira Engineering  
> **Published at:** [https://olira.ai/api-docs](https://olira.ai/api-docs) → Python SDK tab  
> **Status:** **BETA** — SDK APIs and this reference may change between releases.

# Olira Python SDK — API Reference

The Olira Python SDK provides a typed client for logging health events,
managing patients, backfilling historical data, reading Patient State,
and minting patient-scoped tokens for use with the
[Olira MCP Patient State server](https://olira.ai/api-docs).

**Package:** `olira` — **Version:** `1.0.8`

## Related docs

| Doc                                                                             | What it covers                                               | Why you need it                                                                                                                                                             |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Authentication** ([api-docs](https://olira.ai/api-docs) → Authentication tab) | API keys, patient tokens, **scopes**, auth errors            | Choose scopes when creating keys; mint patient tokens for device-facing calls                                                                                               |
| **MCP Patient State** ([api-docs](https://olira.ai/api-docs) → MCP tab)         | Tools for querying patient health state from AI agents       | The events you log with this SDK populate the patient state the MCP server exposes; `get_patient_token()` mints the tokens used to authenticate patient-facing MCP requests |
| **CLI** ([api-docs](https://olira.ai/api-docs) → CLI tab)                       | `olira login`, `olira keys create`, `olira configure cursor` | Create and rotate the API keys passed to `olira.init()`; configure Cursor to use the MCP server                                                                             |

## Scopes

Each API key carries one or more scopes. Assign only what your integration needs.

| Scope                   | What it unlocks                                                   |
| ----------------------- | ----------------------------------------------------------------- |
| `sdk:event-log`         | `log()`, `log_batch()`, `log_fhir()`                              |
| `api:manage-patients`   | `create_patient()`, `update_patient()`, `delete_patient()`, etc.  |
| `sdk:patient-token`     | `get_patient_token()`                                             |
| `sdk:historical-ingest` | `create_ingestion_job()` and all job management methods           |
| `sdk:state-read`        | All `get_stable_data()`, `get_view()`, `get_logs()`, etc. methods |
| `mcp:patient-state`     | Query patient state via the MCP Patient State server              |

## Getting Started

### Installation

```bash
pip install olira
```

Or with `uv`:

```bash
uv add olira
```

### Quickstart

The shortest path to a working integration — initialise, create a patient, log an event, flush:

```python
import olira
from olira import OliraLogType

olira.init(api_key="YOUR_OLIRA_API_KEY")

# 1. Create a patient — store the returned id in your database
patient = olira.create_patient(first_name="Ada", last_name="Lovelace", timezone="UTC")

# 2. Log a health event — enqueued for background delivery
olira.log(
    log_type=OliraLogType.SYMPTOM_REPORT,
    patient_id=patient.id,
    payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 3}]},
)

# 3. Flush before process exit to drain the background queue
olira.flush()
```

See [`examples/`](examples/) for runnable scripts covering patients, logging, FHIR ingestion, historical backfill, state read, and patient tokens.

### Initialise the client

```python
import olira

olira.init(api_key="YOUR_OLIRA_API_KEY")
```

The API key can also be supplied via the `OLIRA_API_KEY` environment variable:

```python
import os, olira

os.environ["OLIRA_API_KEY"] = "YOUR_OLIRA_API_KEY"
olira.init()
```

Use `OliraClient` directly when you need multiple keys or prefer dependency injection:

```python
from olira import OliraClient

client = OliraClient(api_key="YOUR_OLIRA_API_KEY")
```

Production requests go to `https://app-api.prod.olira.ai/app-api` by default (`DEFAULT_BASE_URL`).
`OliraClient`, `AsyncOliraClient`, and `init()` all use that value when `base_url` is omitted.

### `init()` — module-level initialisation

#### `init`

```python
init(api_key: str | None = None, *, environment: OliraEnv = OliraEnv.PRODUCTION, service_name: str | None = None, base_url: str = 'https://app-api.prod.olira.ai/app-api', batch_size: int = 50, flush_interval: float = 1.5, max_queue_size: int = 10000, timeout: float = 5.0, max_retries: int = 3, on_error: str = 'drop', async_flush: bool = True) -> None
```

Initialize the SDK. API key can be passed or set via `OLIRA_API_KEY` env var.

| Parameter        | Required | Type            | Default                                   | Description                                                                                                                                                                                          |
| ---------------- | -------- | --------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api_key`        | No       | `Optional[str]` | `None`                                    | API key; falls back to `OLIRA_API_KEY` env var.                                                                                                                                                      |
| `environment`    | No       | `OliraEnv`      | `OliraEnv.PRODUCTION`                     | `DEVELOPMENT` tags events for non-production systems; use `PRODUCTION` for live data.                                                                                                                |
| `service_name`   | No       | `Optional[str]` | `None`                                    | Optional label attached to every event's `context` for observability (e.g. `"my-service"`).                                                                                                          |
| `base_url`       | No       | `str`           | `'https://app-api.prod.olira.ai/app-api'` | Override for local dev or staging.                                                                                                                                                                   |
| `batch_size`     | No       | `int`           | `50`                                      | Max events per `/v1/logs/batch` request sent by the background worker.                                                                                                                               |
| `flush_interval` | No       | `float`         | `1.5`                                     | Seconds between automatic background flushes.                                                                                                                                                        |
| `max_queue_size` | No       | `int`           | `10000`                                   | Max events held in the in-process queue; `on_error` applies when full.                                                                                                                               |
| `timeout`        | No       | `float`         | `5.0`                                     | Per-request HTTP timeout in seconds.                                                                                                                                                                 |
| `max_retries`    | No       | `int`           | `3`                                       | Retry attempts for 429 / 5xx responses before raising.                                                                                                                                               |
| `on_error`       | No       | `str`           | `'drop'`                                  | What to do when the queue is full or a batch fails after retries: `'drop'` silently discards, `'raise'` raises an exception, or pass a `Callable[[Exception, list[str]], None]` for custom handling. |
| `async_flush`    | No       | `bool`          | `True`                                    | `True` starts a background worker thread that batches and sends events automatically. Set `False` for scripts or tests where you want synchronous delivery via `log_batch()`.                        |

#### `flush`

```python
flush() -> None
```

Block until all queued events have been delivered (or failed). Call this before process exit in long-running services, or at the end of scripts.

```python
olira.log(log_type=OliraLogType.USER_LOGIN, patient_id="patient-uuid")
olira.flush()  # wait for delivery before the process exits
```

## Olira CLI

The CLI ships separately and provides local tooling for API key management
and Cursor configuration. Install it with Homebrew:

```bash
brew install olira-ai/tap/olira
```

Or download a binary directly from [GitHub Releases](https://github.com/olira-ai/olira-cli/releases).

### Creating an API key with the CLI

```bash
olira login
olira keys create --name "my-key" --scopes sdk:event-log api:manage-patients
```

### Other useful commands

```bash
olira status          # Show login status and token expiry
olira token           # Print access token to stdout
olira keys list       # List all API keys for your org
olira keys revoke my-key
olira configure cursor  # Write MCP server config to .cursor/mcp.json
```

## Models

### `OliraTrace`

`OliraTrace` is an optional provenance field you can attach to any `log()` or
`log_batch()` call to record which object in your own system produced the event.

**When to use it:** pass a trace whenever an event is generated as a side-effect
of something else in your application — a conversation turn that surfaces a
symptom, a questionnaire submission, an AI agent interaction. The trace is stored
alongside the event and returned in `get_recent_event_logs` results from the MCP,
giving you a complete line-of-sight from a raw event back to its originating
object without any extra lookups.

`object_id` is your identifier for that object — the same string you would use
to look it up in your own database. It is stored and returned as-is and is never
interpreted or validated by Olira.

| Field         | Required | Type  | Description                                                                          |
| ------------- | -------- | ----- | ------------------------------------------------------------------------------------ |
| `object_type` | Yes\*    | `str` | Category of the linked object, e.g. `'conversation'`, `'message'`, `'questionnaire'` |
| `object_id`   | Yes\*    | `str` | Your identifier for the linked object                                                |

\*Required when sending a trace via `log()` or `log_batch()`. Either field may be `null` on logs returned by `get_logs()` (e.g. historically ingested events).

**Example:**

```python
from olira import OliraTrace, OliraLogType

# A symptom report extracted from a conversation turn
olira.log(
    log_type=OliraLogType.SYMPTOM_REPORT,
    patient_id="patient-uuid",
    payload={
        "instrument": "esas_r",
        "symptoms": [{"name": "nausea", "score": 5}],
    },
    trace=OliraTrace(
        object_type="conversation",
        object_id="conv-abc-123",   # your conversation ID
    ),
)
```

The trace is visible in the event log returned by `get_recent_event_logs` on the
MCP Patient State server, so your agents can see exactly which conversation
produced a given data point.

### `OliraLogType`

`StrEnum` of all supported log types. Use these constants as `log_type`
in `log()` and `log_batch()`.

**Symptom reports**

- `OliraLogType.SYMPTOM_REPORT` → `"symptom_report"`
- `OliraLogType.SYMPTOM_FREE_TEXT` → `"symptom_free_text"`
- `OliraLogType.SYMPTOM_DETAIL` → `"symptom_detail"`
- `OliraLogType.MOODS_REPORT` → `"moods_report"`
- `OliraLogType.FUNCTIONAL_CLASS_REPORTED` → `"functional_class_reported"`
- `OliraLogType.HEALTH_METRIC_REPORTED` → `"health_metric_reported"`

**Lab & clinical**

- `OliraLogType.LAB_RESULTS_RECEIVED` → `"lab_results_received"`
- `OliraLogType.VITALS_MEASUREMENT` → `"vitals_measurement"`
- `OliraLogType.CLINICAL_NOTE_RECEIVED` → `"clinical_note_received"`
- `OliraLogType.CLINICAL_FINDING_REPORTED` → `"clinical_finding_reported"`
- `OliraLogType.PROCEDURE_RESULT_RECEIVED` → `"procedure_result_received"`
- `OliraLogType.PROCEDURE_PERFORMED` → `"procedure_performed"`
- `OliraLogType.GENOMIC_VARIANT_REPORTED` → `"genomic_variant_reported"`
- `OliraLogType.IMAGING_RESULT_RECEIVED` → `"imaging_result_received"`
- `OliraLogType.CLINICAL_MEASUREMENT_REPORTED` → `"clinical_measurement_reported"`
- `OliraLogType.TREATMENT_RESPONSE_ASSESSMENT_REPORTED` → `"treatment_response_assessment_reported"`
- `OliraLogType.CLINICAL_PLAN_ITEM_REPORTED` → `"clinical_plan_item_reported"`
- `OliraLogType.CARE_ENCOUNTER_REPORTED` → `"care_encounter_reported"`
- `OliraLogType.CARE_GOAL_REPORTED` → `"care_goal_reported"`
- `OliraLogType.IMMUNIZATION_REPORTED` → `"immunization_reported"`
- `OliraLogType.ALLERGY_INTOLERANCE_REPORTED` → `"allergy_intolerance_reported"`
- `OliraLogType.FAMILY_HISTORY_REPORTED` → `"family_history_reported"`
- `OliraLogType.DEVICE_REPORTED` → `"device_reported"`
- `OliraLogType.CARE_ACTION_LOGGED` → `"care_action_logged"`
- `OliraLogType.MEMORY_REPORT` → `"memory_report"`
- `OliraLogType.UNSTRUCTURED_REPORT_RECEIVED` → `"unstructured_report_received"`

**Questionnaires**

- `OliraLogType.QUESTIONNAIRE_RESPONSE` → `"questionnaire_response"`
- `OliraLogType.QUESTIONNAIRE_ITEM_RESPONSE` → `"questionnaire_item_response"`

**Conversations**

- `OliraLogType.CONVERSATION_COMPLETED` → `"conversation_completed"`
- `OliraLogType.CONVERSATION_TURN_LOGGED` → `"conversation_turn_logged"`

**Passive data**

- `OliraLogType.HEART_RATE_DATA_RECEIVED` → `"heart_rate_data_received"`
- `OliraLogType.SLEEP_DATA_RECEIVED` → `"sleep_data_received"`
- `OliraLogType.ACTIVITY_DATA_RECEIVED` → `"activity_data_received"`
- `OliraLogType.CGM_READING_RECEIVED` → `"cgm_reading_received"`
- `OliraLogType.SPO2_READING_RECEIVED` → `"spo2_reading_received"`
- `OliraLogType.WEIGHT_MEASUREMENT_RECEIVED` → `"weight_measurement_received"`

**Medications**

- `OliraLogType.MEDICATION_ACTION` → `"medication_action"`
- `OliraLogType.MEDICATION_DOSE_UPDATE` → `"medication_dose_update"`
- `OliraLogType.MEDICATION_ADVERSE_EVENT_REPORTED` → `"medication_adverse_event_reported"`

**Engagement**

- `OliraLogType.USER_LOGIN` → `"user_login"`
- `OliraLogType.USER_LOGOUT` → `"user_logout"`
- `OliraLogType.CONTENT_INTERACTED` → `"content_interacted"`
- `OliraLogType.NOTIFICATION_INTERACTED` → `"notification_interacted"`
- `OliraLogType.TASK_UPDATED` → `"task_updated"`
- `OliraLogType.INTERACTION_FEEDBACK` → `"interaction_feedback"`
- `OliraLogType.FEATURE_USED` → `"feature_used"`

**Profile**

- `OliraLogType.DEMOGRAPHICS_UPDATED` → `"demographics_updated"`
- `OliraLogType.CONDITION_RECORDED` → `"condition_recorded"`
- `OliraLogType.PREFERENCES_UPDATED` → `"preferences_updated"`
- `OliraLogType.EMERGENCY_CONTACT_UPDATED` → `"emergency_contact_updated"`
- `OliraLogType.CARE_TEAM_UPDATED` → `"care_team_updated"`
- `OliraLogType.INSURANCE_UPDATED` → `"insurance_updated"`
- `OliraLogType.SOCIAL_UPDATED` → `"social_updated"`
- `OliraLogType.PHARMACY_UPDATED` → `"pharmacy_updated"`
- `OliraLogType.TREATMENT_PHASE_CHANGED` → `"treatment_phase_changed"`

## Patients

All patient functions require an API key with `api:manage-patients` scope.

### Create a patient

#### `create_patient`

```python
create_patient(
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone_number: str | None = None,
    date_of_birth: str | None = None,
    sex: str = "unknown",
    timezone: str = "UTC",
    primary_disease_site: str | None = None,
    disease_stage: str | None = None,
    external_identifiers: list[ExternalIdentifier] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Patient
```

Create a patient. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope. Returns a `Patient`
with an Olira-assigned `id` — use it in all subsequent calls for this patient.

**Anchor rule (validation):** You must provide **at least one** of: a non-empty `external_identifiers` list, `email`, non-empty `phone_number`, `first_name`, `last_name`, or `date_of_birth`. Omitting all of these raises a validation error. This allows **shell** patients (for example, an external EMR id only) until demographics are synced or entered later via `update_patient`.

| Parameter              | Required | Type                               | Default               |
| ---------------------- | -------- | ---------------------------------- | --------------------- |
| `first_name`           | No       | `str \| None`                      | `None`                |
| `last_name`            | No       | `str \| None`                      | `None`                |
| `email`                | No       | `str \| None`                      | `None`                |
| `phone_number`         | No       | `str \| None`                      | `None`                |
| `date_of_birth`        | No       | `str \| None`                      | `None`                |
| `sex`                  | No       | `str`                              | `'unknown'`           |
| `timezone`             | No       | `str`                              | `'UTC'`               |
| `primary_disease_site` | No       | `str \| None`                      | `None`                |
| `disease_stage`        | No       | `str \| None`                      | `None`                |
| `external_identifiers` | No       | `list[ExternalIdentifier] \| None` | `None` (sent as `[]`) |
| `metadata`             | No       | `dict[str, Any] \| None`           | `None`                |

`date_of_birth` must be ISO 8601 when provided (for example `1985-03-22T00:00:00Z`).

**Examples:**

```python
from olira import ExternalIdentifier

# Full demographics
patient = olira.create_patient(
    first_name="Jane",
    last_name="Smith",
    email="jane@example.com",
    date_of_birth="1985-03-22T00:00:00Z",
    sex="female",
    timezone="America/New_York",
    primary_disease_site="breast",
    disease_stage="Stage II",
    external_identifiers=[ExternalIdentifier(system="epic", value="MRN-12345")],
)
print(patient.id)  # Olira-assigned ID — use in all subsequent calls
```

```python
from olira import ExternalIdentifier

# Shell patient: external id only (names / DOB omitted until available)
patient = olira.create_patient(
    external_identifiers=[ExternalIdentifier(system="epic", value="Patient/abc123")],
)
```

### List patients

#### `list_patients`

```python
list_patients(*, limit: int = 100, offset: int = 0, external_system: str | None = None, external_value: str | None = None) -> PatientListResult
```

List patients in your organisation. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope.

| Parameter         | Required | Type            | Default |
| ----------------- | -------- | --------------- | ------- |
| `limit`           | No       | `int`           | `100`   |
| `offset`          | No       | `int`           | `0`     |
| `external_system` | No       | `Optional[str]` | `None`  |
| `external_value`  | No       | `Optional[str]` | `None`  |

**Example:**

```python
result = olira.list_patients(limit=20, offset=0)
for patient in result.patients:
    print(patient.id, patient.first_name, patient.last_name)
```

### Get a patient

#### `get_patient`

```python
get_patient(*, patient_id: str) -> Patient
```

Get a patient by their id. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope.

| Parameter    | Required | Type  | Default |
| ------------ | -------- | ----- | ------- |
| `patient_id` | Yes      | `str` | —       |

**Example:**

```python
patient = olira.get_patient(patient_id="patient-uuid")
```

### Update a patient

#### `update_patient`

```python
update_patient(*, patient_id: str, first_name: str | None = None, last_name: str | None = None, email: str | None = None, phone_number: str | None = None, sex: str | None = None, timezone: str | None = None, primary_disease_site: str | None = None, disease_stage: str | None = None, external_identifiers: list[ExternalIdentifier] | None = None, metadata: dict[str, Any] | None = None) -> Patient
```

Update a patient. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope.
Only supplied fields are changed; omitted fields are left as-is.

| Parameter              | Required | Type                                 | Default |
| ---------------------- | -------- | ------------------------------------ | ------- |
| `patient_id`           | Yes      | `str`                                | —       |
| `first_name`           | No       | `Optional[str]`                      | `None`  |
| `last_name`            | No       | `Optional[str]`                      | `None`  |
| `email`                | No       | `Optional[str]`                      | `None`  |
| `phone_number`         | No       | `Optional[str]`                      | `None`  |
| `sex`                  | No       | `Optional[str]`                      | `None`  |
| `timezone`             | No       | `Optional[str]`                      | `None`  |
| `primary_disease_site` | No       | `Optional[str]`                      | `None`  |
| `disease_stage`        | No       | `Optional[str]`                      | `None`  |
| `external_identifiers` | No       | `Optional[list[ExternalIdentifier]]` | `None`  |
| `metadata`             | No       | `Optional[dict[str, Any]]`           | `None`  |

Only the fields you supply are changed; omitted fields are left as-is.

**Example:**

```python
olira.update_patient(
    patient_id="patient-uuid",
    disease_stage="Stage III",
    primary_disease_site="lung",
)
```

### External Identifiers

Link a patient to their ID in another system using `ExternalIdentifier`:

```python
from olira import ExternalIdentifier

olira.update_patient(
    patient_id="patient-uuid",
    external_identifiers=[
        ExternalIdentifier(system="epic", value="MRN-12345"),
        ExternalIdentifier(system="flatiron", value="FLT-67890"),
    ],
)
```

### Delete a patient

#### `delete_patient`

```python
delete_patient(*, patient_id: str) -> None
```

Soft-delete a patient. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope.

| Parameter    | Required | Type  | Default |
| ------------ | -------- | ----- | ------- |
| `patient_id` | Yes      | `str` | —       |

Soft-deletes the patient. The record is retained for audit purposes.

### Batch create patients

#### `create_patients_batch`

```python
create_patients_batch(patients: list[CreatePatientRequest]) -> PatientBatchResult
```

Batch-create up to 500 patients. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope. Partial success is supported.
Returns a `PatientBatchResult` with items (successes) and errors (failures).

| Parameter  | Required | Type                         | Default |
| ---------- | -------- | ---------------------------- | ------- |
| `patients` | Yes      | `list[CreatePatientRequest]` | —       |

**Example:**

```python
from olira import CreatePatientRequest, ExternalIdentifier

result = olira.create_patients_batch([
    CreatePatientRequest(
        first_name="Alice",
        last_name="Jones",
        date_of_birth="1990-01-15T00:00:00Z",
        sex="female",
        timezone="UTC",
    ),
    CreatePatientRequest(
        external_identifiers=[ExternalIdentifier(system="epic", value="Patient/shell-1")],
    ),
])
print(f"Created {result.count}, errors: {len(result.errors)}")
```

### Patient response models

### `ExternalIdentifier`

Links a patient to their ID in an external system (e.g. Epic MRN, Flatiron ID, FHIR resource ID).

| Field    | Required | Type  | Description                                  |
| -------- | -------- | ----- | -------------------------------------------- |
| `system` | Yes      | `str` | System name, e.g. 'epic', 'flatiron', 'fhir' |
| `value`  | Yes      | `str` | Patient ID in that system                    |

### `CreatePatientRequest`

Request body for creating a patient (including batch create).

Olira assigns a stable `id` at creation time — it is returned on the `Patient` response. The same **anchor rule** as `create_patient` applies: at least one of `external_identifiers` (non-empty), `email`, `phone_number`, `first_name`, `last_name`, or `date_of_birth` must be set. Optional demographics support **shell** patients.

| Field                  | Required | Type                       | Description                                             |
| ---------------------- | -------- | -------------------------- | ------------------------------------------------------- |
| `first_name`           | No       | `str \| None`              | Given name; omit for shell patients.                    |
| `last_name`            | No       | `str \| None`              | Family name; omit for shell patients.                   |
| `email`                | No       | `str \| None`              | —                                                       |
| `phone_number`         | No       | `str \| None`              | —                                                       |
| `date_of_birth`        | No       | `str \| None`              | ISO 8601 when set, e.g. `1985-03-22T00:00:00Z`.         |
| `sex`                  | No       | `str`                      | Default `'unknown'`.                                    |
| `timezone`             | No       | `str`                      | Default `'UTC'`.                                        |
| `primary_disease_site` | No       | `str \| None`              | —                                                       |
| `disease_stage`        | No       | `str \| None`              | —                                                       |
| `external_identifiers` | No       | `list[ExternalIdentifier]` | Default `[]`. Non-empty list satisfies the anchor rule. |
| `metadata`             | No       | `dict[str, Any] \| None`   | —                                                       |

### `UpdatePatientRequest`

Request body for updating a patient (all fields optional).

Only the fields you set are changed; omitted fields are left as-is.

| Field                  | Required | Type                                 | Description         |
| ---------------------- | -------- | ------------------------------------ | ------------------- |
| `first_name`           | No       | `Optional[str]`                      | — (default: `None`) |
| `last_name`            | No       | `Optional[str]`                      | — (default: `None`) |
| `email`                | No       | `Optional[str]`                      | — (default: `None`) |
| `phone_number`         | No       | `Optional[str]`                      | — (default: `None`) |
| `sex`                  | No       | `Optional[str]`                      | — (default: `None`) |
| `timezone`             | No       | `Optional[str]`                      | — (default: `None`) |
| `primary_disease_site` | No       | `Optional[str]`                      | — (default: `None`) |
| `disease_stage`        | No       | `Optional[str]`                      | — (default: `None`) |
| `external_identifiers` | No       | `Optional[list[ExternalIdentifier]]` | — (default: `None`) |
| `metadata`             | No       | `Optional[dict[str, Any]]`           | — (default: `None`) |

### `Patient`

A patient in your organisation.

`id` is the Olira-assigned identifier for this patient, returned at creation
time. Use it in all subsequent calls that reference this patient.

Demographics may be absent for shell patients created with only an external id or partial data; `first_name`, `last_name`, and `sex` are then `None`.

| Field                  | Required | Type                       | Description        |
| ---------------------- | -------- | -------------------------- | ------------------ |
| `id`                   | Yes      | `str`                      | Olira-assigned id. |
| `first_name`           | No       | `str \| None`              | `None` if unknown. |
| `last_name`            | No       | `str \| None`              | `None` if unknown. |
| `sex`                  | No       | `str \| None`              | `None` if unknown. |
| `timezone`             | Yes      | `str`                      | IANA timezone.     |
| `status`               | Yes      | `str`                      | Account status.    |
| `email`                | No       | `str \| None`              | —                  |
| `phone_number`         | No       | `str \| None`              | —                  |
| `date_of_birth`        | No       | `str \| None`              | ISO 8601 when set. |
| `primary_disease_site` | No       | `str \| None`              | —                  |
| `disease_stage`        | No       | `str \| None`              | —                  |
| `created_at`           | No       | `str \| None`              | —                  |
| `external_identifiers` | No       | `list[ExternalIdentifier]` | May be empty.      |
| `metadata`             | No       | `dict[str, Any] \| None`   | —                  |

### `PatientListResult`

Result of a list_patients() call.

| Field      | Required | Type            | Description |
| ---------- | -------- | --------------- | ----------- |
| `patients` | Yes      | `list[Patient]` | —           |
| `total`    | Yes      | `int`           | —           |
| `has_more` | Yes      | `bool`          | —           |

### `PatientBatchItem`

One successfully created patient from a batch_create_patients() call.

| Field    | Required | Type            | Description         |
| -------- | -------- | --------------- | ------------------- |
| `index`  | Yes      | `int`           | —                   |
| `id`     | Yes      | `str`           | —                   |
| `source` | No       | `Optional[str]` | — (default: `None`) |

### `PatientBatchResult`

Result of a create_patients_batch() call. Mirrors /v1/patients/batch response.

| Field    | Required | Type                     | Description           |
| -------- | -------- | ------------------------ | --------------------- |
| `count`  | Yes      | `int`                    | —                     |
| `items`  | Yes      | `list[PatientBatchItem]` | —                     |
| `errors` | No       | `list[BatchError]`       | — (default: `list()`) |

### `PatientToken`

A short-lived patient-scoped JWT returned by get_patient_token().

Pass `access_token` as a Bearer token to the Olira MCP Patient State server.
The token is locked to the patient identified by the `patient_id` you supplied
and expires after `expires_in` seconds (default 15 minutes).

| Field          | Required | Type        | Description             |
| -------------- | -------- | ----------- | ----------------------- |
| `access_token` | Yes      | `str`       | —                       |
| `token_type`   | No       | `str`       | — (default: `'bearer'`) |
| `expires_in`   | Yes      | `int`       | —                       |
| `scopes`       | Yes      | `list[str]` | —                       |

## Logs

All log functions require `sdk:event-log` scope.

Use `log()` and `log_batch()` for **ongoing operational traffic**—applications, integrations, and moderate batch sizes where each submission should update patient state through Olira's immediate graph-update path.

Use `log_fhir()` when your source data is already in **FHIR R4 format**. Olira maps the resource to one or more platform log types via the same absorber used by Epic/Cerner integrations, so you don't need to choose a `log_type` or build Olira-shaped payloads yourself.

For **bulk historical data** (e.g. months or years at once, or onboarding backfills before go-live), use **[Historical Data Ingestion](#historical-data-ingestion)** with `create_ingestion_job()` and the **`sdk:historical-ingest`** scope. That pipeline stages rows, replays them in chronological order, and backfills summary views — not `log_batch` at volume.

### Log a single event

#### `log`

```python
log(*, log_type: OliraLogType, patient_id: str, payload: dict[str, Any] | None = None, trace: OliraTrace | None = None, timestamp: str | None = None, metadata: dict[str, Any] | None = None) -> None
```

Enqueue an event for background delivery. Module-level proxy to the singleton client.

| Parameter    | Required | Type                       | Default |
| ------------ | -------- | -------------------------- | ------- |
| `log_type`   | Yes      | `OliraLogType`             | —       |
| `patient_id` | Yes      | `str`                      | —       |
| `payload`    | No       | `Optional[dict[str, Any]]` | `None`  |
| `trace`      | No       | `Optional[OliraTrace]`     | `None`  |
| `timestamp`  | No       | `Optional[str]`            | `None`  |
| `metadata`   | No       | `Optional[dict[str, Any]]` | `None`  |

Events are enqueued and flushed in the background. Call `olira.flush()` before
process exit to ensure delivery.

**Example:**

```python
import olira
from olira import OliraLogType

olira.log(
    log_type=OliraLogType.SYMPTOM_REPORT,
    patient_id="patient-uuid",
    payload={
        "instrument": "esas_r",
        "symptoms": [
            {"name": "pain", "score": 4},
            {"name": "fatigue", "score": 6},
        ],
    },
)
olira.flush()
```

**With trace (provenance):**

```python
from olira import OliraLogType, OliraTrace

# Attribute the event back to the conversation that produced it
olira.log(
    log_type=OliraLogType.SYMPTOM_REPORT,
    patient_id="patient-uuid",
    payload={
        "instrument": "esas_r",
        "symptoms": [{"name": "fatigue", "score": 6}],
    },
    trace=OliraTrace(object_type="conversation", object_id="conv-abc-123"),
)
olira.flush()
```

### Log a batch of events

#### `log_batch`

```python
log_batch(events: list[LogSpec]) -> BatchResult
```

Send a batch of events directly. Module-level proxy to the singleton client.

| Parameter | Required | Type            | Default |
| --------- | -------- | --------------- | ------- |
| `events`  | Yes      | `list[LogSpec]` | —       |

**Example:**

```python
from olira import LogSpec, OliraLogType

result = olira.log_batch([
    LogSpec(
        log_type=OliraLogType.VITALS_MEASUREMENT,
        patient_id="patient-uuid",
        payload={
            "measurements": {"systolic_bp_mmhg": 128, "diastolic_bp_mmhg": 82,
                               "heart_rate_bpm": 72, "spo2_percent": None,
                               "weight_kg": None, "temperature_celsius": None,
                               "respiratory_rate_bpm": None},
            "context": {"position": "sitting", "fasting": None},
            "source": "manual_entry",
            "collection_datetime": "2026-03-18T09:00:00Z",
        },
    ),
    LogSpec(
        log_type=OliraLogType.MEDICATION_DOSE_UPDATE,
        patient_id="patient-uuid",
        payload={
            "medication_adherence": [{"status": "taken", "medication_name": "Ondansetron 4mg"}],
        },
    ),
])
print(f"Accepted: {result.accepted}, Failed: {result.failed}")
```

### Log a FHIR resource

#### `log_fhir`

```python
log_fhir(*, patient_id: str, resource: dict[str, Any]) -> BatchResult
```

Submit a single FHIR R4 resource for immediate ingestion. Module-level proxy to the singleton client.

Olira maps the resource to one or more platform log types via the FHIR absorber (the same schema mapper used by Epic/Cerner integrations) and processes each resulting event immediately for the patient. You do not choose `log_type` or build Olira-shaped payloads — the absorber handles the mapping.

Requires `sdk:event-log` scope.

| Parameter    | Required | Type             | Default |
| ------------ | -------- | ---------------- | ------- |
| `patient_id` | Yes      | `str`            | —       |
| `resource`   | Yes      | `dict[str, Any]` | —       |

`resource` must be a valid FHIR R4 JSON object with a `resourceType` field. Supported types include `Condition`, `MedicationRequest`, `MedicationStatement`, `MedicationAdministration`, `AllergyIntolerance`, `Appointment`, `Encounter`, `Procedure`, `Immunization`, `DiagnosticReport`, `DocumentReference`, `CarePlan`, `CareTeam`, `FamilyMemberHistory`, `Goal`, `Observation` (vital-signs), and `Patient`.

**Raises `ValidationError`** if:

- `resourceType` is missing (HTTP 422 from the API)
- The resource maps to zero Olira events — unsupported type, unrecognized fields, or (for `Observation`) unrecognized category/LOINC code. The exception message explains why.

**Example — ingest a Condition:**

```python
import olira

olira.init(api_key="YOUR_API_KEY")

result = olira.log_fhir(
    patient_id="patient-uuid",
    resource={
        "resourceType": "Condition",
        "id": "condition-1",
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}],
        },
        "code": {
            "coding": [{"system": "http://snomed.info/sct", "code": "254837009", "display": "Breast cancer"}],
            "text": "Breast cancer",
        },
        "subject": {"reference": "Patient/example"},
        "onsetDateTime": "2025-01-10T00:00:00Z",
    },
)
print(f"Accepted: {result.accepted}")
```

**Example — error handling:**

```python
from olira import ValidationError

try:
    result = olira.log_fhir(
        patient_id="patient-uuid",
        resource={"resourceType": "SupplyDelivery", "status": "completed"},
    )
except ValidationError as e:
    print(f"Resource not supported: {e}")
```

### Log response models

### `LogSpec`

Lightweight event specification for log_batch(). Not persisted internally.

| Field             | Required | Type                       | Description                                                                                                                               |
| ----------------- | -------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `log_type`        | Yes      | `OliraLogType`             | —                                                                                                                                         |
| `patient_id`      | Yes      | `str`                      | —                                                                                                                                         |
| `payload`         | No       | `Optional[dict[str, Any]]` | — (default: `None`)                                                                                                                       |
| `trace`           | No       | `Optional[OliraTrace]`     | — (default: `None`)                                                                                                                       |
| `timestamp`       | No       | `Optional[str]`            | — (default: `None`)                                                                                                                       |
| `idempotency_key` | No       | `Optional[str]`            | — (default: `None`)                                                                                                                       |
| `metadata`        | No       | `Optional[dict[str, Any]]` | Arbitrary key/value context stored separately from the typed payload. Surfaced in the Olira Console event detail panel. (default: `None`) |

### `BatchResult`

Result of a log_batch() call. Mirrors /v1/logs/batch response.

| Field      | Required | Type               | Description           |
| ---------- | -------- | ------------------ | --------------------- |
| `accepted` | Yes      | `int`              | —                     |
| `failed`   | Yes      | `int`              | —                     |
| `errors`   | No       | `list[BatchError]` | — (default: `list()`) |

### `BatchError`

Per-event error from a batch response.

| Field     | Required | Type  | Description |
| --------- | -------- | ----- | ----------- |
| `index`   | Yes      | `int` | —           |
| `code`    | Yes      | `str` | —           |
| `message` | Yes      | `str` | —           |

## Patient Token

Patient tokens are short-lived JWTs scoped to a single patient. They are the bridge between your server-side API key and patient-facing or agent-facing calls to the [Olira MCP Patient State server](https://olira.ai/api-docs).

**When to use:**

- An AI agent needs to query a specific patient's state via the MCP server — mint a token and pass it as the Bearer header for that session
- A patient-facing device or frontend needs to read its own state — your backend mints the token on demand and forwards it; the client never sees your API key

**When not to use:**

- Server-to-server calls from your own backend — use your API key directly with `sdk:state-read` scope instead

Tokens expire after **15 minutes** (`expires_in: 900`). They are locked to the patient supplied at mint time — a token for patient A cannot query patient B. Mint a fresh token for each MCP session or device request; there is no refresh mechanism.

Requires `sdk:patient-token` scope.

### Mint a patient-scoped JWT

#### `get_patient_token`

```python
get_patient_token(*, patient_id: str) -> PatientToken
```

| Parameter    | Required | Type  | Default |
| ------------ | -------- | ----- | ------- |
| `patient_id` | Yes      | `str` | —       |

**Basic example:**

```python
import olira

olira.init(api_key="YOUR_API_KEY")
token = olira.get_patient_token(patient_id="patient-uuid")

print(token.access_token)  # forward to the agent or device
print(f"Expires in {token.expires_in}s")  # 900
print(token.scopes)        # e.g. ["sdk:state-read", "sdk:event-log"]
```

**Forwarding to an MCP client (httpx example):**

```python
import httpx, olira

olira.init(api_key="YOUR_API_KEY")

def get_fresh_token(patient_id: str) -> str:
    tok = olira.get_patient_token(patient_id=patient_id)
    return tok.access_token

# Mint per session — tokens expire in 15 minutes
bearer = get_fresh_token("patient-uuid")

resp = httpx.post(
    "https://mcp.prod.olira.ai/mcp",
    headers={"Authorization": f"Bearer {bearer}"},
    json={"method": "get_view", "params": {"view_type": "weekly_health_summary"}},
)
```

**Handling expiry:**

```python
import time, olira
from olira import AuthError

olira.init(api_key="YOUR_API_KEY")

class PatientSession:
    def __init__(self, patient_id: str) -> None:
        self.patient_id = patient_id
        self._token = None
        self._expires_at = 0.0

    def bearer(self) -> str:
        if time.time() >= self._expires_at - 30:  # 30s buffer
            tok = olira.get_patient_token(patient_id=self.patient_id)
            self._token = tok.access_token
            self._expires_at = time.time() + tok.expires_in
        return self._token
```

## Patient State — Read

The state-read methods give Python backends direct access to the same compiled patient state that the [MCP Patient State server](https://olira.ai/api-docs) exposes to AI agents — without going through JSON-RPC. They are a REST-backed mirror of the MCP tools, returning raw structured data rather than agent-formatted text.

All state-read functions require an API key with the `sdk:state-read` scope.

| SDK method                 | MCP tool equivalent                   |
| -------------------------- | ------------------------------------- |
| `get_stable_data`          | `get_stable_data`                     |
| `list_event_state_modules` | `list_event_state_modules`            |
| `get_event_state_module`   | `get_event_state_module`              |
| `list_views`               | `list_views_and_blocks` (list mode)   |
| `list_view_blocks`         | `list_views_and_blocks` (blocks mode) |
| `get_view`                 | `get_view`                            |
| `get_view_block`           | `get_view_block`                      |
| `get_view_recent_events`   | `get_view_recent_events`              |
| `get_logs`                 | `get_logs`                            |
| `get_events`               | `get_events`                          |
| `read_memories`            | `read_memories` (list-all mode)       |

**Key differences from the MCP:**

- Returns raw structured data — no pretty-printed markdown rendering
- `read_memories(query=...)` uses MongoDB text search; the MCP uses Qdrant semantic search
- The SDK does not expose memory writes; use ingestion APIs and platform workflows to persist new clinical facts

---

### Stable data

#### `get_stable_data`

```python
get_stable_data(*, patient_id: str, modules: list[str] | None = None) -> StableDataResult
```

Get stable patient data (demographics, condition/diagnosis, medications, preferences). Mirrors `get_stable_data` on the MCP.

| Parameter    | Required | Type                | Default      |
| ------------ | -------- | ------------------- | ------------ |
| `patient_id` | Yes      | `str`               | —            |
| `modules`    | No       | `list[str] \| None` | `None` (all) |

Valid module names (`StableModuleType`): `demographics`, `condition_diagnosis`, `medications`, `user_preferences`, `emergency_contact`, `care_team`, `insurance`, `social`, `pharmacy`, `procedures`, `allergies`, `immunizations`, `devices`, `family_history`, `treatment_phase`. Which are populated depends on what data has been ingested for this patient. Omit `modules` to fetch all.

**Example:**

```python
result = olira.get_stable_data(patient_id="patient-uuid")
demo = result.modules.get("demographics")
if demo:
    print(demo.payload)
```

**Mock response:**

```json
{
  "patient_id": "507f1f77bcf86cd799439011",
  "modules": {
    "demographics": {
      "module_type": "demographics",
      "payload": {
        "value": {
          "first_name": "Jane",
          "last_name": "Smith",
          "date_of_birth": "1975-06-15",
          "sex": "female",
          "timezone": "America/New_York"
        }
      },
      "created_at": "2026-01-10T08:00:00+00:00",
      "updated_at": "2026-03-18T14:22:00+00:00"
    },
    "condition_diagnosis": {
      "module_type": "condition_diagnosis",
      "payload": {
        "value": {
          "primary_disease_site": "breast",
          "disease_stage": "Stage II"
        }
      },
      "created_at": "2026-01-10T08:00:00+00:00",
      "updated_at": "2026-01-10T08:00:00+00:00"
    }
  }
}
```

---

### Event state modules

#### `list_event_state_modules`

```python
list_event_state_modules(*, patient_id: str) -> list[EventStateModuleSummary]
```

List event state module types present for the patient.

**Example:**

```python
modules = olira.list_event_state_modules(patient_id="patient-uuid")
for m in modules:
    print(m.module_type, m.updated_at)
```

**Mock response (list items):**

```json
[
  {
    "module_type": "symptoms",
    "updated_at": "2026-03-18T10:00:00+00:00",
    "created_at": "2026-01-10T08:00:00+00:00"
  },
  {
    "module_type": "adherence",
    "updated_at": "2026-03-17T09:30:00+00:00",
    "created_at": "2026-01-10T08:00:00+00:00"
  },
  {
    "module_type": "engagement",
    "updated_at": "2026-03-18T12:00:00+00:00",
    "created_at": "2026-01-10T08:00:00+00:00"
  }
]
```

#### `get_event_state_module`

```python
get_event_state_module(*, patient_id: str, module_type: str) -> EventStateModuleResult
```

Get a specific event state module by type. Mirrors `get_event_state_module` on the MCP.

Valid module types (`EventStateModuleType`): `symptoms`, `behavioral_state`, `adherence`, `physical_activity`, `engagement`, `heart`, `sleep`, `lab_results`, `vitals`, `clinical_context`, `questionnaires`, `conversations`, `glucose`, `alerts_and_tasks`. Use `list_event_state_modules()` to discover which are present and populated for a specific patient.

**Example:**

```python
module = olira.get_event_state_module(patient_id="patient-uuid", module_type="symptoms")
print(module.payload)
```

**Mock response:**

```json
{
  "patient_id": "507f1f77bcf86cd799439011",
  "module_type": "symptoms",
  "payload": {
    "week_symptoms": [
      {
        "name": "pain",
        "score": 4,
        "ctcae_grade": 1,
        "updated_at": "2026-03-18T10:00:00+00:00"
      },
      {
        "name": "fatigue",
        "score": 6,
        "ctcae_grade": 2,
        "updated_at": "2026-03-18T10:00:00+00:00"
      }
    ],
    "functional_class_history": []
  },
  "created_at": "2026-01-10T08:00:00+00:00",
  "updated_at": "2026-03-18T10:00:00+00:00"
}
```

> **Note:** Payload shape is module-type-specific and org-configured. The `symptoms` module uses `week_symptoms` / `functional_class_history`; other modules have different shapes. Treat `payload` as an opaque dict — its structure mirrors what the MCP's `get_event_state_module` returns in `format: "raw"` mode.

---

### Patient views

#### `list_views`

```python
list_views(*, patient_id: str) -> list[ViewMeta]
```

List available view types for the patient.

**Example:**

```python
views = olira.list_views(patient_id="patient-uuid")
for v in views:
    print(v.view_type, v.has_blocks, v.has_temp)
```

**Mock response (list items):**

```json
[
  {
    "view_type": "symptom_snapshot",
    "view_id": "66f1a2b3c4d5e6f7a8b9c0d1",
    "has_blocks": true,
    "has_temp": true
  },
  {
    "view_type": "medication_snapshot",
    "view_id": "66f1a2b3c4d5e6f7a8b9c0d2",
    "has_blocks": true,
    "has_temp": true
  }
]
```

#### `list_view_blocks`

```python
list_view_blocks(*, patient_id: str, view_type: str) -> ViewBlocksListResult
```

List blocks within a specific view. Returns the unified block list (`content.blocks`).

**Example:**

```python
result = olira.list_view_blocks(patient_id="patient-uuid", view_type="symptom_snapshot")
for block in result.blocks:
    print(block.block_id, block.has_result)
```

#### `get_view`

```python
get_view(*, patient_id: str, view_type: str) -> ViewResult
```

Get a compiled patient view snapshot. Returns the unified block list under `content["blocks"]`
plus live TEMP entries under `content["temp"]` when present.

| Parameter    | Required | Type  | Default |
| ------------ | -------- | ----- | ------- |
| `patient_id` | Yes      | `str` | —       |
| `view_type`  | Yes      | `str` | —       |

**Example:**

```python
view = olira.get_view(
    patient_id="patient-uuid",
    view_type="symptom_snapshot",
)
print(view.content)
```

**Mock response:**

```json
{
  "patient_id": "507f1f77bcf86cd799439011",
  "view_type": "symptom_snapshot",
  "view_id": "66f1a2b3c4d5e6f7a8b9c0d1",
  "valid_from": "2026-03-11T00:00:00+00:00",
  "valid_to": "2026-03-18T00:00:00+00:00",
  "content": {
    "blocks": [
      {
        "id": "symptom_overview",
        "name": "Symptom Overview",
        "text": "Patient reported moderate pain (4/10) and significant fatigue (6/10) over the past 7 days."
      },
      {
        "id": "symptom_trends",
        "name": "Symptom Trends",
        "text": "Fatigue has been stable week-over-week. Pain has increased from 3/10 to 4/10."
      }
    ],
    "temp": [
      "2026-03-18 10:00 — symptom_report: pain 4/10, fatigue 6/10 (esas_r)"
    ]
  }
}
```

#### `get_view_block`

```python
get_view_block(*, patient_id: str, view_type: str, block_id: str) -> ViewBlockResult
```

Get a specific block from the unified block list.

**Example:**

```python
block = olira.get_view_block(
    patient_id="patient-uuid",
    view_type="symptom_snapshot",
    block_id="symptom_overview",
)
print(block.content, block.confidences)
```

#### `get_view_recent_events`

```python
get_view_recent_events(*, patient_id: str, view_type: str, limit: int = 50) -> ViewRecentEventsResult
```

Get live TEMP entries for a view (appended as events arrive, no AI processing lag).

**Example:**

```python
recent = olira.get_view_recent_events(
    patient_id="patient-uuid",
    view_type="symptom_snapshot",
    limit=10,
)
for entry in recent.entries:
    print(entry)
```

**Mock response:**

```json
{
  "patient_id": "507f1f77bcf86cd799439011",
  "view_type": "symptom_snapshot",
  "entries": [
    "2026-03-18 10:00 — symptom_report: pain 4/10, fatigue 6/10 (esas_r)",
    "2026-03-17 09:15 — symptom_report: nausea 2/10, pain 3/10 (esas_r)"
  ],
  "count": 2,
  "total_count": 14
}
```

---

### Logs & events

#### `get_logs`

```python
get_logs(
    *,
    patient_id: str,
    since: str | None = None,
    limit: int = 50,
    log_types: list[str] | None = None,
    trace_type: str | None = None,
    trace_id: str | None = None,
) -> LogsResult
```

Get event logs with optional filters.

| Parameter    | Required | Type                | Default |
| ------------ | -------- | ------------------- | ------- |
| `patient_id` | Yes      | `str`               | —       |
| `since`      | No       | `str \| None`       | `None`  |
| `limit`      | No       | `int`               | `50`    |
| `log_types`  | No       | `list[str] \| None` | `None`  |
| `trace_type` | No       | `str \| None`       | `None`  |
| `trace_id`   | No       | `str \| None`       | `None`  |

**Examples:**

```python
# Recent symptom and vitals events
logs = olira.get_logs(
    patient_id="patient-uuid",
    since="2026-03-11T00:00:00Z",
    log_types=["symptom_report", "vitals_measurement"],
)

# Events tied to a specific conversation
logs = olira.get_logs(
    patient_id="patient-uuid",
    trace_type="conversation",
    trace_id="conv-abc-123",
)
for entry in logs.logs:
    print(entry.type, entry.timestamp, entry.payload)
```

**Mock response:**

```json
{
  "patient_id": "507f1f77bcf86cd799439011",
  "count": 2,
  "logs": [
    {
      "id": "66f1a2b3c4d5e6f7a8b9c0d3",
      "type": "symptom_report",
      "timestamp": "2026-03-18T10:00:00+00:00",
      "payload": {
        "instrument": "esas_r",
        "symptoms": [
          { "name": "pain", "score": 4 },
          { "name": "fatigue", "score": 6 }
        ]
      },
      "trace": { "object_type": "conversation", "object_id": "conv-abc-123" }
    },
    {
      "id": "66f1a2b3c4d5e6f7a8b9c0d4",
      "type": "moods_report",
      "timestamp": "2026-03-18T10:01:00+00:00",
      "payload": { "moods": [{ "mood": "anxious", "intensity": 3 }] },
      "trace": { "object_type": "conversation", "object_id": "conv-abc-123" }
    }
  ]
}
```

#### `get_events`

```python
get_events(
    *,
    patient_id: str,
    since: str | None = None,
    log_type: str | None = None,
    trace_type: str | None = None,
    trace_id: str | None = None,
    status: str = "complete",
    limit: int = 50,
) -> EventsResult
```

Get events driven by logs. When `trace_type` / `trace_id` / `log_type` are supplied, the server first resolves matching EventLog IDs where applicable, then returns events driven by those logs.

**Example:**

```python
events = olira.get_events(
    patient_id="patient-uuid",
    trace_type="conversation",
    trace_id="conv-abc-123",
)
for t in events.events:
    print(t.log_type, t.triggered_at, t.changes)
```

---

### Memories

#### `read_memories`

```python
read_memories(*, patient_id: str, query: str | None = None, limit: int = 100) -> MemoriesResult
```

Read patient memories. Pass `query` for text-based search; omit to list all.

> **Note:** `query` uses MongoDB substring search, not the semantic (vector) search the MCP uses. For semantic retrieval, use `read_memories` on the MCP server directly. List-all (no `query`) is identical between the SDK and MCP.

| Parameter    | Required | Type          | Default |
| ------------ | -------- | ------------- | ------- |
| `patient_id` | Yes      | `str`         | —       |
| `query`      | No       | `str \| None` | `None`  |
| `limit`      | No       | `int`         | `100`   |

**Example:**

```python
memories = olira.read_memories(patient_id="patient-uuid", query="fatigue")
for m in memories.results:
    print(m.memory_id, m.content)
```

**Mock response:**

```json
{
  "patient_id": "507f1f77bcf86cd799439011",
  "count": 2,
  "results": [
    {
      "memory_id": "mem-001",
      "content": "Patient reports fatigue worsens in the afternoon after chemotherapy sessions.",
      "metadata": null,
      "created_at": "2026-03-01T09:00:00+00:00",
      "updated_at": "2026-03-01T09:00:00+00:00"
    },
    {
      "memory_id": "mem-002",
      "content": "Patient mentioned fatigue is interfering with daily activities, especially cooking.",
      "metadata": null,
      "created_at": "2026-03-10T14:30:00+00:00",
      "updated_at": "2026-03-10T14:30:00+00:00"
    }
  ]
}
```

---

### State-read response models

### `StableModule`

| Field         | Type           | Description        |
| ------------- | -------------- | ------------------ |
| `module_type` | `str`          | Module key         |
| `payload`     | `dict \| None` | Raw module data    |
| `created_at`  | `str \| None`  | ISO 8601 timestamp |
| `updated_at`  | `str \| None`  | ISO 8601 timestamp |

### `StableDataResult`

| Field        | Type                      | Description           |
| ------------ | ------------------------- | --------------------- |
| `patient_id` | `str`                     | Patient ID            |
| `modules`    | `dict[str, StableModule]` | Modules keyed by type |

### `EventStateModuleSummary`

| Field         | Type          | Description        |
| ------------- | ------------- | ------------------ |
| `module_type` | `str`         | Module type key    |
| `updated_at`  | `str \| None` | ISO 8601 timestamp |
| `created_at`  | `str \| None` | ISO 8601 timestamp |

### `EventStateModuleResult`

| Field         | Type                   | Description        |
| ------------- | ---------------------- | ------------------ |
| `patient_id`  | `str`                  | Patient ID         |
| `module_type` | `str`                  | Module type        |
| `payload`     | `dict \| list \| None` | Module data        |
| `created_at`  | `str \| None`          | ISO 8601 timestamp |
| `updated_at`  | `str \| None`          | ISO 8601 timestamp |

### `ViewMeta`

| Field        | Type   | Description                   |
| ------------ | ------ | ----------------------------- |
| `view_type`  | `str`  | View type key                 |
| `view_id`    | `str`  | MongoDB document ID           |
| `has_blocks` | `bool` | Unified block list available  |
| `has_temp`   | `bool` | TEMP (live) entries available |

### `ViewResult`

| Field        | Type             | Description                                                   |
| ------------ | ---------------- | ------------------------------------------------------------- |
| `patient_id` | `str`            | Patient ID                                                    |
| `view_type`  | `str`            | View type                                                     |
| `view_id`    | `str \| None`    | MongoDB document ID                                           |
| `valid_from` | `str \| None`    | View coverage start (ISO 8601)                                |
| `valid_to`   | `str \| None`    | View coverage end (ISO 8601)                                  |
| `content`    | `dict[str, Any]` | `"blocks"` → unified block list; `"temp"` → live TEMP entries |

### `ViewBlockResult`

| Field         | Type                       | Description                                                   |
| ------------- | -------------------------- | ------------------------------------------------------------- |
| `patient_id`  | `str`                      | Patient ID                                                    |
| `view_type`   | `str`                      | View type                                                     |
| `block_id`    | `str`                      | Block identifier                                              |
| `content`     | `str \| None`              | Generated block text (raw, without MCP's pretty-print header) |
| `confidences` | `dict[str, float] \| None` | Confidence scores                                             |
| `updated_at`  | `str \| None`              | ISO 8601 timestamp                                            |

### `ViewRecentEventsResult`

| Field         | Type        | Description                        |
| ------------- | ----------- | ---------------------------------- |
| `patient_id`  | `str`       | Patient ID                         |
| `view_type`   | `str`       | View type                          |
| `entries`     | `list[str]` | TEMP entries (most recent `limit`) |
| `count`       | `int`       | Number of entries returned         |
| `total_count` | `int`       | Total TEMP entries in store        |

### `LogEntry`

| Field       | Type                 | Description         |
| ----------- | -------------------- | ------------------- |
| `id`        | `str`                | MongoDB document ID |
| `type`      | `str \| None`        | Event type string   |
| `timestamp` | `str \| None`        | ISO 8601 timestamp  |
| `payload`   | `dict[str, Any]`     | Event payload       |
| `trace`     | `OliraTrace \| None` | Provenance trace    |

### `LogsResult`

| Field        | Type             | Description       |
| ------------ | ---------------- | ----------------- |
| `patient_id` | `str`            | Patient ID        |
| `count`      | `int`            | Number of entries |
| `logs`       | `list[LogEntry]` | Event log entries |

### `EventEntry`

| Field                 | Type           | Description                     |
| --------------------- | -------------- | ------------------------------- |
| `id`                  | `str`          | MongoDB document ID             |
| `trigger`             | `str \| None`  | `event_log` or `summary_block`  |
| `log_type`            | `str \| None`  | Originating event type          |
| `status`              | `str \| None`  | `complete`, `pending`, `failed` |
| `triggered_at`        | `str \| None`  | ISO 8601 timestamp              |
| `completed_at`        | `str \| None`  | ISO 8601 timestamp              |
| `source_event_log_id` | `str \| None`  | Originating EventLog ID         |
| `log_payload`         | `dict \| None` | Payload from the source event   |
| `changes`             | `dict \| None` | State changes applied           |

### `EventsResult`

| Field        | Type               | Description       |
| ------------ | ------------------ | ----------------- |
| `patient_id` | `str`              | Patient ID        |
| `count`      | `int`              | Number of entries |
| `events`     | `list[EventEntry]` | Events            |

### `MemoryEntry`

| Field        | Type           | Description        |
| ------------ | -------------- | ------------------ |
| `memory_id`  | `str`          | Memory identifier  |
| `content`    | `str`          | Memory text        |
| `metadata`   | `dict \| None` | Optional metadata  |
| `created_at` | `str \| None`  | ISO 8601 timestamp |
| `updated_at` | `str \| None`  | ISO 8601 timestamp |

### `MemoriesResult`

| Field        | Type                | Description       |
| ------------ | ------------------- | ----------------- |
| `patient_id` | `str`               | Patient ID        |
| `count`      | `int`               | Number of results |
| `results`    | `list[MemoryEntry]` | Memory records    |

## Async Client

All methods are available on `AsyncOliraClient` as coroutines. Use it as an async context manager:

```python
import asyncio
from olira import AsyncOliraClient, OliraLogType

async def main():
    async with AsyncOliraClient(api_key="YOUR_API_KEY") as client:
        patient = await client.create_patient(first_name="Ada", last_name="Lovelace")

        await client.log(
            log_type=OliraLogType.SYMPTOM_REPORT,
            patient_id=patient.id,
            payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 3}]},
        )
        await client.flush()

asyncio.run(main())
```

`AsyncOliraClient` accepts the same constructor parameters as `OliraClient`. The context manager (`async with`) handles transport lifecycle — call `await client.aclose()` explicitly if you manage the client outside a `with` block.

Every method on `OliraClient` has a direct async equivalent: `await client.create_patient(...)`, `await client.log_fhir(...)`, `await client.get_view(...)`, and so on.

## Error Handling

All SDK errors inherit from `OliraError`.

| Exception         | Inherits     | Description                                                                                 |
| ----------------- | ------------ | ------------------------------------------------------------------------------------------- |
| `OliraError`      | `Exception`  | Base exception for all Olira SDK errors.                                                    |
| `AuthError`       | `OliraError` | Raised on 401 Unauthorized or 403 Forbidden — invalid or revoked API key.                   |
| `RateLimitError`  | `OliraError` | Raised on 429 Too Many Requests. Includes retry_after from Retry-After header.              |
| `ValidationError` | `OliraError` | Raised on 422 or client-side validation failure (malformed event, PII in patient_id, etc.). |
| `ServerError`     | `OliraError` | Raised on 409 Conflict or 5xx server-side failure after retries exhausted.                  |
| `NetworkError`    | `OliraError` | Raised on connection timeout, DNS failure, or other network error after retries exhausted.  |

**Example:**

```python
from olira import AuthError, RateLimitError, ValidationError
import time

try:
    olira.log(log_type=OliraLogType.SYMPTOM_REPORT, patient_id="...", payload={...})
    olira.flush()
except AuthError:
    print("Invalid or revoked API key — check your credentials")
except RateLimitError as e:
    print(f"Rate limited — retry after {e.retry_after}s")
    time.sleep(e.retry_after)
except ValidationError as e:
    print(f"Validation error: {e}")
```

## Common Log Payloads

### `symptom_report`

```python
olira.log(
    log_type=OliraLogType.SYMPTOM_REPORT,
    patient_id="patient-uuid",
    payload={
        "instrument": "esas_r",
        "symptoms": [
            {"name": "pain", "score": 4},
            {"name": "tiredness", "score": 6},
            {"name": "nausea", "score": 1},
        ],
    },
)
```

### `lab_results_received`

```python
olira.log(
    log_type=OliraLogType.LAB_RESULTS_RECEIVED,
    patient_id="patient-uuid",
    payload={
        "collection_datetime": "2026-03-18T07:30:00Z",
        "results": [
            {
                "loinc_code": "718-7",
                "test_name": "Hemoglobin",
                "value_numeric": 11.2,
                "unit": "g/dL",
                "abnormal_flag": "L",
                "reference_range_low": 12.0,
                "reference_range_high": 16.0,
            }
        ],
    },
)
```

### `medication_action`

```python
olira.log(
    log_type=OliraLogType.MEDICATION_ACTION,
    patient_id="patient-uuid",
    payload={
        "medications": [
            {
                "action": "add",
                "rxnorm_cui": "1049502",
                "medication_name": "Ondansetron 4mg",
                "dose": "4 mg",
                "frequency": "every 8h as needed",
                "route": "oral",
                "start_date": "2026-03-18",
                "schedule_times": ["08:00", "16:00", "00:00"],
            }
        ],
    },
)
```

### `conversation_completed`

```python
olira.log(
    log_type=OliraLogType.CONVERSATION_COMPLETED,
    patient_id="patient-uuid",
    payload={
        "conversation_id": "conv-abc-123",
        "channel": "chat",
        "transcript": [
            {"speaker_label": "agent", "text": "How are you feeling today?"},
            {"speaker_label": "patient", "text": "My nausea has improved but I'm still fatigued."},
        ],
    },
)
```

---

## Historical Data Ingestion

Bulk-load months or years of existing patient health data before going live.
The ingestion pipeline validates records, creates patients, inserts logs as `STALE` rows,
replays them through the graph in chronological order, and backfills summary views —
making imported data fully queryable in the Olira Console.

**Requires** an API key with the `sdk:historical-ingest` scope.

### Overview

```
Phase 1 (automatic after job creation):
  QUEUED → VALIDATING → INSERTING_PATIENTS → INSERTING_LOGS → AWAITING_CONFIRMATION

Phase 2 (triggered by the customer):
  CONFIRMED → REPLAYING → BACKFILLING → COMPLETED
```

By default the job pauses at `AWAITING_CONFIRMATION` so you can review patient and log
counts before committing to the expensive graph replay. Pass `require_confirmation=False`
to run straight through.

### Quickstart — file upload (recommended for large datasets)

```python
import olira, time

olira.init(api_key="YOUR_sdk:historical-ingest_KEY")

# Create the job — SDK streams the file to S3 automatically
job = olira.create_ingestion_job(
    file="patients_and_logs.jsonl",
    idempotency_key="initial-onboarding-2026",   # optional but recommended
)

# Phase 1 — poll every 10 s until paused for review (typically seconds to minutes)
while job.status not in ("awaiting_confirmation", "completed", "failed"):
    time.sleep(10)
    job = olira.get_ingestion_job(job_id=job.job_id)
    print(f"{job.stage}  {job.progress_pct:.0f}%")

# Review what was created before committing to graph replay
print(f"Patients: {job.patients_processed}")
print(f"Logs:     {job.logs_processed} inserted, {job.logs_failed} failed")
if job.error_summary:
    print(f"First errors (up to 100 shown):")
    for err in job.error_summary:
        print(f"  Line {err.line}: {err.code} — {err.message}")
    if job.logs_failed > len(job.error_summary):
        print(f"  … and {job.logs_failed - len(job.error_summary)} more (re-run with a corrected file)")

# Confirm to start Phase 2 (graph replay + view backfill)
job = olira.confirm_ingestion_job(job_id=job.job_id)

# Phase 2 — poll every 30 s; replay can take minutes to hours depending on volume
while job.status not in ("completed", "completed_with_errors", "failed"):
    time.sleep(30)
    job = olira.get_ingestion_job(job_id=job.job_id)
    eta = f"  ETA ~{job.estimated_seconds_remaining}s" if job.estimated_seconds_remaining else ""
    print(f"{job.stage}  {job.progress_pct:.0f}%{eta}")
```

### Quickstart — inline records (for smaller datasets, ≤ 50,000 records)

```python
import olira
from olira import IngestRecord, IngestLogSpec, CreatePatientRequest, ExternalIdentifier

job = olira.create_ingestion_job(
    records=[
        IngestRecord.patient(CreatePatientRequest(
            first_name="Jane",
            last_name="Smith",
            date_of_birth="1980-03-22T00:00:00Z",
            external_identifiers=[ExternalIdentifier(system="epic", value="MRN-12345")],
        )),
        IngestRecord.log(IngestLogSpec(
            event_type="symptom_report",
            # patient_id can be an external_identifier value (any system) or an Olira patient UUID
            patient_id="MRN-12345",
            # timestamp backdates the event — this is how historical events are placed correctly
            # in the patient timeline. Use ISO 8601 with timezone offset or trailing 'Z'.
            timestamp="2025-01-15T09:00:00Z",
            payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 3}]},
            idempotency_key="report-001",    # strongly recommended — prevents duplicates on retry
        )),
    ],
    idempotency_key="lab-backfill-batch-1",
    require_confirmation=False,              # run straight through without review pause
)
```

### JSONL file format

The JSONL file accepted by `file=` contains one JSON object per line. Two record types:

```jsonl
{"type": "patient", "data": {"first_name": "Jane", "last_name": "Smith", "date_of_birth": "1980-03-22T00:00:00Z", "timezone": "America/New_York", "external_identifiers": [{"system": "epic", "value": "MRN-12345"}]}}
{"type": "log",     "data": {"event_type": "symptom_report", "patient_id": "MRN-12345", "timestamp": "2025-01-15T09:00:00Z", "payload": {"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 3}]}, "idempotency_key": "report-001"}}
{"type": "log",     "data": {"event_type": "lab_results_received", "patient_id": "MRN-12345", "timestamp": "2024-03-15T09:00:00Z", "payload": {"results": []}, "trace": {"object_type": "emr_record", "object_id": "epic-encounter-98765"}}}
```

**Patient fields** match `CreatePatientRequest`. At least one of `external_identifiers`,
`email`, `phone_number`, `first_name`, `last_name`, or `date_of_birth` is required.

**Log fields:**

- `event_type` (required) — must be a valid platform event type (e.g. `"symptom_report"`, `"lab_results_received"`).
- `patient_id` (required) — resolved server-side in this order: (1) if it parses as an Olira patient UUID, it is resolved server-side against your org's patients — a UUID from a different org or a mistyped UUID is rejected; (2) otherwise, it is matched against every `external_identifier.value` in the file and in your org, across all systems. The first matching patient wins. If no patient is found via either path, the log is rejected with `code: "missing_patient"` in `error_summary`. This covers: a nonexistent UUID, a UUID belonging to a different org, or an external ID that doesn't match any patient in the file or your org. Note: local pre-flight validation (`validate_ingestion_file()`) can only check within-file references — UUID org membership is only verifiable server-side.
- `timestamp` (required) — ISO 8601 datetime, e.g. `"2025-01-15T09:00:00Z"`. **This is how historical events are placed at their correct point in the patient timeline.** Logs are sorted by `timestamp` per patient before graph replay, so ordering in the file does not matter.
- `payload` (optional) — event-specific data.
- `idempotency_key` (optional but strongly recommended) — if this log is submitted again in a retry job, the duplicate is silently skipped. Without it, retrying a failed job will insert duplicate log rows.
- `trace` (optional) — provenance link to an object in your system (`object_type`, `object_id`). Same rules as live `log()`: when present, both fields must be non-empty strings. Most backfills omit this; use it when you need `get_logs(trace_type=...)` filtering on ingested events (e.g. `"emr_record"` / `"epic-encounter-98765"`).

Patient and log records may appear in any order. The pipeline collects all patients first, then resolves all log `patient_id` references — so a log appearing before its patient in the file is fine.

### File size and performance guidance

- **File size limit: 100 MB.** `validate_ingestion_file()` and `create_ingestion_job()` both reject files larger than this before making any network call. The limit is configurable server-side; the SDK reads it from the upload URL response.
- **For very large datasets (millions of rows), split into batches** of ~100k–500k records per job. This keeps the review window manageable and limits the blast radius if a job fails.
- **Phase 1 (validate + insert)** typically takes seconds to a few minutes regardless of file size.
- **Phase 2 (replay) runtime** scales with the number of patients and events: expect roughly 0.1–2 seconds per patient per log, depending on event complexity. A job with 10,000 patients and 50 logs each could take 1–3 hours. Use `estimated_seconds_remaining` in the poll loop to track progress.
- **Webhooks are not currently supported.** Poll `get_ingestion_job()` every 10–30 seconds during Phase 1 and every 30–60 seconds during Phase 2.

### Local pre-flight validation

`create_ingestion_job()` automatically validates the file or records before making any network call. If validation fails it raises `ValidationError` immediately — no upload, no job created, no wasted request.

You can also run validation explicitly to get the full error list before deciding whether to submit:

```python
errors = olira.validate_ingestion_file("patients_and_logs.jsonl")
if errors:
    for e in errors:
        print(f"Line {e.line}: [{e.code}] {e.message}")
else:
    job = olira.create_ingestion_job(file="patients_and_logs.jsonl")
```

For inline records: `olira.validate_ingestion_records(records)` — same checks, operates on a `list[IngestRecord]`.

**What is checked locally (no network required):**

- Each line is valid JSON
- `type` is `"patient"` or `"log"`
- Patient anchor rule (at least one identifying field)
- Log required fields: `event_type`, `patient_id`, `timestamp`
- `event_type` is a known platform type — with typo suggestions (e.g. `"lab_result_receivd"` → did you mean `"lab_results_received"?`)
- `timestamp` is parseable ISO 8601
- `patient_id` resolves to a patient defined anywhere in the same file (order-agnostic)
- Optional `trace`: when present, `object_type` and `object_id` must be non-empty strings

**What requires a server call (checked by Stage 1):**

- Whether `patient_id` refers to an existing org patient not in this file
- Whether the event payload matches the server-side JSON Schema for that event type

### `create_ingestion_job`

```python
create_ingestion_job(
    *,
    file: str | None = None,
    records: list[IngestRecord] | None = None,
    idempotency_key: str | None = None,
    require_confirmation: bool = True,
    rollback_on_cancel: bool = False,
    summary_types: list[str] | None = None,
    max_event_logs: int | None = None,
) -> IngestionJob
```

| Parameter              | Required                | Type                 | Default | Description                                                                                                                                                                                                                                                                                            |
| ---------------------- | ----------------------- | -------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `file`                 | One of `file`/`records` | `str`                | —       | Path to a JSONL file. SDK handles S3 upload. Max 100 MB — `ValidationError` raised before upload if exceeded. For larger datasets, split into multiple jobs.                                                                                                                                           |
| `records`              | One of `file`/`records` | `list[IngestRecord]` | —       | Inline records (≤ 50,000). For larger datasets use `file=`.                                                                                                                                                                                                                                            |
| `idempotency_key`      | No                      | `str`                | `None`  | Prevents duplicate jobs on retry. Returns 409 if an active or successfully completed job with this key exists. If the previous job failed, a new job is created instead.                                                                                                                               |
| `require_confirmation` | No                      | `bool`               | `True`  | Pause at `AWAITING_CONFIRMATION` for review before Phase 2. Set `False` to run straight through.                                                                                                                                                                                                       |
| `rollback_on_cancel`   | No                      | `bool`               | `False` | Controls what happens to **patients** when the job is cancelled. STALE logs are **always** deleted on cancel regardless of this setting (an unprocessed STALE log with no future replay job is meaningless). Set `True` to also delete created patients on cancel.                                     |
| `summary_types`        | No                      | `list[str]`          | `None`  | Which view types to backfill in Phase 2. `None` = all view templates active for your org. Valid values are the `summary_type` identifiers on your org's active templates (e.g. `"emotional_state_snapshot"`, `"symptom_snapshot"`). You can update this via `patch_ingestion_job()` before confirming. |
| `max_event_logs`       | No                      | `int`                | `None`  | **Per-patient** cap on the number of event logs considered during view backfill. Logs above the cap are skipped **for backfill only** — they are fully inserted and permanently stored. This is a cost-control knob for orgs with extremely log-dense patients. Omit for standard use.                 |

### `get_ingestion_job`

```python
get_ingestion_job(*, job_id: str) -> IngestionJob
```

Poll the current status of a job.

**Recommended polling cadence:**

- Phase 1 (up to `AWAITING_CONFIRMATION`): every **10 seconds**
- Phase 2 (`REPLAYING` / `BACKFILLING`): every **30–60 seconds** — replay is slow by design (sequential per patient to avoid state corruption). Use `estimated_seconds_remaining` to set user expectations.

### `list_ingestion_jobs`

```python
list_ingestion_jobs(
    *,
    idempotency_key: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> IngestionJobListResult
```

List all ingestion jobs for your organisation, newest first.
Filter by `idempotency_key` to retrieve a specific job by the key you supplied at creation.

### `confirm_ingestion_job`

```python
confirm_ingestion_job(*, job_id: str) -> IngestionJob
```

Confirm a job in `AWAITING_CONFIRMATION` to trigger Phase 2 (graph replay + view backfill).
Only available while the job is paused at `AWAITING_CONFIRMATION`.

> **Note:** Jobs in `AWAITING_CONFIRMATION` that are not acted on within 7 days are automatically cancelled.

### `cancel_ingestion_job`

```python
cancel_ingestion_job(*, job_id: str) -> IngestionJob
```

Cancel a job. Behaviour depends on the current status:

- **`AWAITING_CONFIRMATION`** — immediate cleanup. STALE logs are always deleted. If `rollback_on_cancel=True` was set at job creation, created patients are also deleted; otherwise patients are retained.
- **`REPLAYING` / `BACKFILLING`** — cooperative stop. The current patient finishes processing before the job stops. Already-replayed patients are **not** rolled back — their state and events persist permanently.

> **STALE log cleanup:** Regardless of `rollback_on_cancel`, cancelling a job always deletes all STALE logs associated with it. An unprocessed STALE log has no replay job to process it and would occupy space indefinitely.

### `delete_ingestion_job_patient`

```python
delete_ingestion_job_patient(*, job_id: str, patient_id: str) -> None
```

Remove a patient and their STALE logs while the job is `AWAITING_CONFIRMATION`.
Useful when you spot a patient that was uploaded by mistake.
Only allowed during the review window; once confirmed, patients are locked.

### `patch_ingestion_job`

```python
patch_ingestion_job(*, job_id: str, summary_types: list[str] | None = None) -> IngestionJob
```

Update mutable fields while the job is `AWAITING_CONFIRMATION`.
Use this to change which view types are backfilled before confirming.
Valid values for `summary_types` are the `summary_type` identifiers on your org's active templates.

### `retry_view_backfill`

```python
retry_view_backfill(*, job_id: str) -> IngestionJob
```

Retry a failed `ViewBackfillJob` on a `COMPLETED_WITH_ERRORS` job.
Patient and log data are fully intact — only view materialisation failed.
Transitions the job back to `BACKFILLING`.

### Job failure and retry

Two terminal error states exist with different recovery paths:

#### `FAILED` — job did not complete

Caused by validation failures (all rows invalid), a missing S3 file, or an unrecoverable system error during Stages 1–4.

**Data state:** STALE logs inserted before the failure remain in the database. Patient documents created in Stage 2 are retained. (`rollback_on_cancel` has no effect on `FAILED` jobs — it only applies to explicit cancellation.)

**Recovery:** Submit a new job. Per-log `idempotency_key` dedup in the retry job skips any logs whose `event_id` already exists from the previous attempt — preventing duplicates. Patients from the failed job are upserted rather than re-created.

The original `idempotency_key` is **reusable** after a `FAILED` job — the server creates a new job rather than returning 409. Only `COMPLETED` and `COMPLETED_WITH_ERRORS` block reuse (data was imported successfully).

```python
# First job failed — safe to reuse the original idempotency_key
job = olira.create_ingestion_job(
    file="patients_and_logs.jsonl",
    idempotency_key="onboarding-2026",  # reusable since the prior job FAILED
)
```

#### `COMPLETED_WITH_ERRORS` — data imported, views not materialised

The patient data and logs are **fully intact and queryable**. Phase 2 replay completed but the view backfill (`ViewBackfillJob`) failed — typically because the org has no active view templates, or a transient error in the view generation pipeline.

**Recovery:** Use `retry_view_backfill()` to re-run the backfill without re-ingesting any data.

```python
if job.status == "completed_with_errors":
    job = olira.retry_view_backfill(job_id=job.job_id)
    # Poll again until completed
    while job.status not in ("completed", "completed_with_errors", "failed"):
        time.sleep(30)
        job = olira.get_ingestion_job(job_id=job.job_id)
```

#### Per-patient replay failures

During Phase 2, if a patient's log fails graph replay, that patient is marked `PatientReplayStatus.FAILED` in `patient_replay_statuses` and the job continues with other patients. The job may still reach `COMPLETED` even with per-patient failures.

To remediate: submit a new job containing only the failed patients' records. Per-log dedup ensures logs for patients that succeeded are not re-inserted.

### Working with `error_summary`

`error_summary` is capped at 100 entries on the job document. If your file has more than 100 invalid rows, the remaining errors are not surfaced directly. **To handle large error volumes:**

1. Check `logs_failed` for the total failure count. If `logs_failed > len(error_summary)`, there are more errors than shown.
2. Fix the errors visible in `error_summary`, then cancel the job and resubmit with a corrected file (per-log `idempotency_key` dedup ensures already-valid rows are not re-inserted).
3. Repeat until `logs_failed == 0` at `AWAITING_CONFIRMATION`.

Most validation errors fall into a small number of categories (`missing_patient`, `invalid_log`, `unknown_record_type`). The first 100 are representative — fixing the root cause typically clears all instances of that error type.

---

### Response models

#### `IngestionJob`

| Field                         | Type                      | Description                                                                                         |
| ----------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------- |
| `job_id`                      | `str`                     | Olira-assigned job identifier                                                                       |
| `status`                      | `IngestionJobStatus`      | Current lifecycle status                                                                            |
| `stage`                       | `str`                     | Human-readable stage description (e.g. `"Replaying logs through graph: 3 of 10 patients complete"`) |
| `progress_pct`                | `float`                   | 0–100 across all stages                                                                             |
| `require_confirmation`        | `bool`                    | Whether the job pauses for review                                                                   |
| `summary_types`               | `list[str]`               | View types to backfill                                                                              |
| `patients_total`              | `int`                     | Patient rows in the file                                                                            |
| `patients_processed`          | `int`                     | Patients successfully upserted                                                                      |
| `logs_total`                  | `int`                     | Log rows in the file                                                                                |
| `logs_processed`              | `int`                     | Logs successfully inserted                                                                          |
| `logs_failed`                 | `int`                     | Logs that failed validation or insert                                                               |
| `logs_by_event_type`          | `dict[str, int]`          | Inserted log count per event type                                                                   |
| `patient_log_counts`          | `dict[str, int]`          | `patient_id → log count` for the review table                                                       |
| `patient_replay_statuses`     | `dict[str, str]`          | `patient_id → "pending"\|"completed"\|"failed"\|"skipped"`                                          |
| `error_summary`               | `list[IngestionRowError]` | Per-row errors (capped at 100)                                                                      |
| `estimated_seconds_remaining` | `int \| None`             | Rough ETA during REPLAYING                                                                          |
| `view_backfill_job_id`        | `str \| None`             | ID of the associated `ViewBackfillJob`                                                              |
| `backfill_status`             | `str \| None`             | Current status of the nested backfill                                                               |
| `backfill_progress_pct`       | `float \| None`           | Progress of the nested backfill                                                                     |
| `created_at`                  | `str \| None`             | ISO 8601 creation time                                                                              |
| `completed_at`                | `str \| None`             | ISO 8601 completion time                                                                            |

#### `IngestionJobStatus`

```python
class IngestionJobStatus(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    INSERTING_PATIENTS = "inserting_patients"
    INSERTING_LOGS = "inserting_logs"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    REPLAYING = "replaying"
    BACKFILLING = "backfilling"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

#### `IngestionRowError`

| Field     | Type  | Description                                                             |
| --------- | ----- | ----------------------------------------------------------------------- |
| `line`    | `int` | 1-indexed line number in the JSONL file (0 = non-row error)             |
| `code`    | `str` | Machine-readable error code (e.g. `"missing_patient"`, `"invalid_log"`) |
| `message` | `str` | Human-readable description                                              |

#### `IngestRecord`

Build via factory methods — do not construct directly:

```python
IngestRecord.patient(req: CreatePatientRequest) -> IngestRecord
IngestRecord.log(spec: IngestLogSpec) -> IngestRecord
```

#### `IngestLogSpec`

| Field             | Type                 | Required | Description                                       |
| ----------------- | -------------------- | -------- | ------------------------------------------------- |
| `event_type`      | `str`                | Yes      | Platform event type (e.g. `"symptom_report"`)     |
| `patient_id`      | `str`                | Yes      | Olira patient UUID or `external_identifier` value |
| `timestamp`       | `str`                | Yes      | ISO 8601 datetime                                 |
| `payload`         | `dict`               | No       | Event-specific payload                            |
| `idempotency_key` | `str`                | No       | Prevents duplicate insertion on retry             |
| `trace`           | `OliraTrace \| None` | No       | Optional provenance; both fields required when set |

#### `IngestionJobListResult`

| Field   | Type                 | Description              |
| ------- | -------------------- | ------------------------ |
| `total` | `int`                | Total jobs for the org   |
| `jobs`  | `list[IngestionJob]` | Jobs in the current page |
