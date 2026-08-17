> **Maintained by:** Olira Engineering  
> **Published at:** [https://docs.olira.ai/reference/sdk](https://docs.olira.ai/reference/sdk)

# Olira Python SDK — API Reference

The Olira Python SDK provides a typed client for logging health events,
managing patients, backfilling historical data, uploading passive sensor
Parquet, reading Patient State, and minting patient-scoped tokens for use with
the [Olira MCP Patient State server](https://docs.olira.ai/mcp-server).

**Package:** `olira` — **Version:** `1.16.0`

## Related docs

| Doc                                                               | What it covers                                               | Why you need it                                                                                                                                                             |
| ----------------------------------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Authentication** ([docs](https://docs.olira.ai/authentication)) | API keys, patient tokens, **scopes**, auth errors            | Choose scopes when creating keys; mint patient tokens for device-facing calls                                                                                               |
| **MCP Patient State** ([docs](https://docs.olira.ai/mcp-server))  | Tools for querying patient health state from AI agents       | The events you log with this SDK populate the patient state the MCP server exposes; `get_patient_token()` mints the tokens used to authenticate patient-facing MCP requests |
| **CLI** ([docs](https://docs.olira.ai/cli))                       | `olira login`, `olira keys create`, `olira configure cursor` | Create and rotate the API keys passed to `olira.init()`; configure Cursor to use the MCP server                                                                             |

## Scopes

Each API key carries one or more scopes. Assign only what your integration needs.

| Scope                   | What it unlocks                                                                                                                                                                                                                                                                                                                                                                         |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sdk:event-log`         | `log()`, `log_batch()`, `log_fhir()`, `upload_document()`, `get_document()`, `OliraClient.send_signals()`, `get_signal_job()`                                                                                                                                                                                                                                                           |
| `api:manage-patients`   | `create_patient()`, `update_patient()`, `delete_patient()`, `create_cohort()`, `add_patients_to_cohort()`, etc.                                                                                                                                                                                                                                                                         |
| `api:manage-projects`   | `create_project()`, `list_projects()`, `get_project()`, `duplicate_project()`, `rename_project()`, `deprecate_project()`, `restore_project()`, `delete_project()` — **requires an org-wide key** (a project-locked key is confined to its own workspace and gets 403).                                                                                                                  |
| `api:org-config`        | Schema/mapping management — `register_schema()`, `list_schemas()`, `get_schema()`, `check_schema()`, `edit_schema()`, `deprecate_schema()`, `activate_schema_version()`                                                                                                                                                                                                                 |
| `sdk:patient-token`     | `get_patient_token()`                                                                                                                                                                                                                                                                                                                                                                   |
| `sdk:historical-ingest` | `create_ingestion_job()` and all job management methods                                                                                                                                                                                                                                                                                                                                 |
| `sdk:state-read`        | All `get_stable_data()`, `get_view()`, `get_logs()`, `logs()` / `population_logs()`, `create_export()` / `get_export()` / `list_exports()` / `download_export()`, etc.                                                                                                                                                                                                                  |
| `sdk:integration-write` | Honors the `write_back` flag on `log()`/`log_batch()` — write-back requests to a connected system (also requires platform-side write configuration)                                                                                                                                                                                                                                                       |
| `sdk:integrations`      | Integration management via the raw `/v1/integrations` REST routes — see [Integrations & Instances](#integrations--instances)                                                                                                                                                                                                                                                    |
| `sdk:actions`           | Outbound-actions destination management and delivery ledger: `create_action_destination()`, `list_action_destinations()`, `get_action_destination()`, `update_action_destination()`, `delete_action_destination()`, `rotate_action_destination_secret()`, `list_action_deliveries()`, `get_action_delivery()`, `redeliver_action_delivery()`. See [Outbound Actions](#outbound-actions) |
| `mcp:patient-state`     | Query patient state via the MCP Patient State server                                                                                                                                                                                                                                                                                                                                    |

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

#### Selecting a project (workspace)

A **project** is an isolated workspace within your organization (its own patients, logs, state, views, cohorts, and configuration — see [Projects](#projects)). Select which project every data call operates in by passing `project` (id or slug) at init:

```python
import olira

# Module-level — or set OLIRA_PROJECT in the environment
olira.init(api_key="YOUR_KEY", project="dev-sandbox")

# Or with the client class
from olira import OliraClient

client = OliraClient(api_key="YOUR_KEY", project="dev-sandbox")
```

Resolution order for every request: the value passed here **>** the `OLIRA_PROJECT` env var **>** the key's own project (for project-locked keys) **>** the org's default project. Under the hood the SDK sends an `X-Olira-Project` header; a **project-locked** key that names a _different_ project is rejected (403). Omit `project` entirely and a project-locked key keeps using its own project, while an otherwise-unscoped (org-wide) key falls back to the org's default project — exactly the pre-projects behavior, so existing integrations keep working unchanged.

### `init()` — module-level initialisation

#### `init`

```python
init(api_key: str | None = None, *, environment: OliraEnv = OliraEnv.PRODUCTION, service_name: str | None = None, project: str | None = None, base_url: str = 'https://app-api.prod.olira.ai/app-api', batch_size: int = 50, flush_interval: float = 1.5, max_queue_size: int = 10000, timeout: float = 5.0, max_retries: int = 3, on_error: str = 'drop', async_flush: bool = True) -> None
```

Initialize the SDK. API key can be passed or set via `OLIRA_API_KEY` env var.

| Parameter        | Required | Type            | Default                                   | Description                                                                                                                                                                                          |
| ---------------- | -------- | --------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api_key`        | No       | `Optional[str]` | `None`                                    | API key; falls back to `OLIRA_API_KEY` env var.                                                                                                                                                      |
| `environment`    | No       | `OliraEnv`      | `OliraEnv.PRODUCTION`                     | `DEVELOPMENT` tags events for non-production systems; use `PRODUCTION` for live data.                                                                                                                |
| `service_name`   | No       | `Optional[str]` | `None`                                    | Optional label attached to every event's `context` for observability (e.g. `"my-service"`).                                                                                                          |
| `project`        | No       | `Optional[str]` | `None`                                    | Project (workspace) id or slug every call operates in; falls back to the `OLIRA_PROJECT` env var. Omit for the org's default project. See [Selecting a project](#selecting-a-project-workspace).     |
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
        object_id="conv-abc-123",  # your conversation ID
    ),
)
```

The trace is visible in the event log returned by `get_recent_event_logs` on the
MCP Patient State server, so your agents can see exactly which conversation
produced a given data point.

### `OliraLogType`

`StrEnum` of all supported log types. Use these constants as `log_type`
in `log()` and `log_batch()`.

The platform renamed most verb-suffixed subtypes to noun-only
canonical names (e.g. `moods_report` → `mood_report`). The platform accepts
both forms indefinitely, so the deprecated members below keep working — but
new integrations should use the canonical name listed alongside each one.

**Symptom reports**

- `OliraLogType.SYMPTOM_REPORT` → `"symptom_report"`
- `OliraLogType.SYMPTOM_FREE_TEXT` → `"symptom_free_text"`
- `OliraLogType.SYMPTOM_DETAIL` → `"symptom_detail"`
- `OliraLogType.MOOD_REPORT` → `"mood_report"` (deprecated alias: `MOODS_REPORT` → `"moods_report"`)
- `OliraLogType.FUNCTIONAL_CLASS` → `"functional_class"` (deprecated alias: `FUNCTIONAL_CLASS_REPORTED` → `"functional_class_reported"`)
- `OliraLogType.HEALTH_METRIC` → `"health_metric"` (deprecated alias: `HEALTH_METRIC_REPORTED` → `"health_metric_reported"`)

**Lab & clinical**

- `OliraLogType.LAB_RESULTS` → `"lab_results"` (deprecated alias: `LAB_RESULTS_RECEIVED` → `"lab_results_received"`)
- `OliraLogType.VITALS_MEASUREMENT` → `"vitals_measurement"`
- `OliraLogType.CLINICAL_NOTE` → `"clinical_note"` (deprecated alias: `CLINICAL_NOTE_RECEIVED` → `"clinical_note_received"`)
- `OliraLogType.CLINICAL_FINDING` → `"clinical_finding"` (deprecated alias: `CLINICAL_FINDING_REPORTED` → `"clinical_finding_reported"`)
- `OliraLogType.PROCEDURE_RESULT` → `"procedure_result"` (deprecated alias: `PROCEDURE_RESULT_RECEIVED` → `"procedure_result_received"`)
- `OliraLogType.PROCEDURE` → `"procedure"` (deprecated alias: `PROCEDURE_PERFORMED` → `"procedure_performed"`)
- `OliraLogType.GENOMIC_VARIANT` → `"genomic_variant"` (deprecated alias: `GENOMIC_VARIANT_REPORTED` → `"genomic_variant_reported"`)
- `OliraLogType.IMAGING_RESULT` → `"imaging_result"` (deprecated alias: `IMAGING_RESULT_RECEIVED` → `"imaging_result_received"`)
- `OliraLogType.CLINICAL_MEASUREMENT` → `"clinical_measurement"` (deprecated alias: `CLINICAL_MEASUREMENT_REPORTED` → `"clinical_measurement_reported"`)
- `OliraLogType.TREATMENT_RESPONSE_ASSESSMENT` → `"treatment_response_assessment"` (deprecated alias: `TREATMENT_RESPONSE_ASSESSMENT_REPORTED` → `"treatment_response_assessment_reported"`)
- `OliraLogType.CLINICAL_PLAN_ITEM` → `"clinical_plan_item"` (deprecated alias: `CLINICAL_PLAN_ITEM_REPORTED` → `"clinical_plan_item_reported"`)
- `OliraLogType.CARE_ENCOUNTER` → `"care_encounter"` (deprecated alias: `CARE_ENCOUNTER_REPORTED` → `"care_encounter_reported"`)
- `OliraLogType.CARE_GOAL` → `"care_goal"` (deprecated alias: `CARE_GOAL_REPORTED` → `"care_goal_reported"`)
- `OliraLogType.IMMUNIZATION` → `"immunization"` (deprecated alias: `IMMUNIZATION_REPORTED` → `"immunization_reported"`)
- `OliraLogType.ALLERGY_INTOLERANCE` → `"allergy_intolerance"` (deprecated alias: `ALLERGY_INTOLERANCE_REPORTED` → `"allergy_intolerance_reported"`)
- `OliraLogType.FAMILY_HISTORY` → `"family_history"` (deprecated alias: `FAMILY_HISTORY_REPORTED` → `"family_history_reported"`)
- `OliraLogType.DEVICE` → `"device"` (deprecated alias: `DEVICE_REPORTED` → `"device_reported"`)
- `OliraLogType.CARE_ACTION` → `"care_action"` (deprecated alias: `CARE_ACTION_LOGGED` → `"care_action_logged"`)
- `OliraLogType.MEMORY_REPORT` → `"memory_report"`
- `OliraLogType.UNSTRUCTURED_REPORT` → `"unstructured_report"` (deprecated alias: `UNSTRUCTURED_REPORT_RECEIVED` → `"unstructured_report_received"`)

**Questionnaires**

- `OliraLogType.QUESTIONNAIRE_RESPONSE` → `"questionnaire_response"`
- `OliraLogType.QUESTIONNAIRE_ITEM_RESPONSE` → `"questionnaire_item_response"`

**Conversations**

- `OliraLogType.CONVERSATION` → `"conversation"` (deprecated alias: `CONVERSATION_COMPLETED` → `"conversation_completed"`)
- `OliraLogType.CONVERSATION_TURN` → `"conversation_turn"` (deprecated alias: `CONVERSATION_TURN_LOGGED` → `"conversation_turn_logged"`)

**Passive data**

- `OliraLogType.HEART_RATE_DATA` → `"heart_rate_data"` (deprecated alias: `HEART_RATE_DATA_RECEIVED` → `"heart_rate_data_received"`)
- `OliraLogType.SLEEP_DATA` → `"sleep_data"` (deprecated alias: `SLEEP_DATA_RECEIVED` → `"sleep_data_received"`)
- `OliraLogType.ACTIVITY_DATA` → `"activity_data"` (deprecated alias: `ACTIVITY_DATA_RECEIVED` → `"activity_data_received"`)
- `OliraLogType.CGM_READING` → `"cgm_reading"` (deprecated alias: `CGM_READING_RECEIVED` → `"cgm_reading_received"`)
- `OliraLogType.SPO2_READING` → `"spo2_reading"` (deprecated alias: `SPO2_READING_RECEIVED` → `"spo2_reading_received"`)
- `OliraLogType.WEIGHT_MEASUREMENT` → `"weight_measurement"` (deprecated alias: `WEIGHT_MEASUREMENT_RECEIVED` → `"weight_measurement_received"`)

**Medications**

- `OliraLogType.MEDICATION_LIST_UPDATE` → `"medication_list_update"` (deprecated alias: `MEDICATION_ACTION` → `"medication_action"`)
- `OliraLogType.MEDICATION_ADHERENCE` → `"medication_adherence"` (deprecated alias: `MEDICATION_DOSE_UPDATE` → `"medication_dose_update"`)
- `OliraLogType.MEDICATION_ADVERSE_EVENT` → `"medication_adverse_event"` (deprecated alias: `MEDICATION_ADVERSE_EVENT_REPORTED` → `"medication_adverse_event_reported"`)

**Engagement**

- `OliraLogType.USER_LOGIN` → `"user_login"`
- `OliraLogType.USER_LOGOUT` → `"user_logout"`
- `OliraLogType.CONTENT_INTERACTION` → `"content_interaction"` (deprecated alias: `CONTENT_INTERACTED` → `"content_interacted"`)
- `OliraLogType.NOTIFICATION_INTERACTION` → `"notification_interaction"` (deprecated alias: `NOTIFICATION_INTERACTED` → `"notification_interacted"`)
- `OliraLogType.TASK_OUTCOME` → `"task_outcome"` (deprecated alias: `TASK_UPDATED` → `"task_updated"`)
- `OliraLogType.INTERACTION_FEEDBACK` → `"interaction_feedback"`
- `OliraLogType.FEATURE_USAGE` → `"feature_usage"` (deprecated alias: `FEATURE_USED` → `"feature_used"`)

**Profile**

- `OliraLogType.DEMOGRAPHICS` → `"demographics"` (deprecated alias: `DEMOGRAPHICS_UPDATED` → `"demographics_updated"`)
- `OliraLogType.CONDITION` → `"condition"` (deprecated alias: `CONDITION_RECORDED` → `"condition_recorded"`)
- `OliraLogType.PREFERENCES` → `"preferences"` (deprecated alias: `PREFERENCES_UPDATED` → `"preferences_updated"`)
- `OliraLogType.EMERGENCY_CONTACT` → `"emergency_contact"` (deprecated alias: `EMERGENCY_CONTACT_UPDATED` → `"emergency_contact_updated"`)
- `OliraLogType.CARE_TEAM` → `"care_team"` (deprecated alias: `CARE_TEAM_UPDATED` → `"care_team_updated"`)
- `OliraLogType.INSURANCE` → `"insurance"` (deprecated alias: `INSURANCE_UPDATED` → `"insurance_updated"`)
- `OliraLogType.SOCIAL_DETERMINANTS` → `"social_determinants"` (deprecated alias: `SOCIAL_UPDATED` → `"social_updated"`)
- `OliraLogType.PHARMACY` → `"pharmacy"` (deprecated alias: `PHARMACY_UPDATED` → `"pharmacy_updated"`)
- `OliraLogType.TREATMENT_PHASE` → `"treatment_phase"` (deprecated alias: `TREATMENT_PHASE_CHANGED` → `"treatment_phase_changed"`)

### Discovering log types live — `list_log_types()` / `get_log_type()`

`OliraLogType` above is the static reference shipped with this SDK version — accurate
as of release, but it can lag the platform if new log types ship between SDK releases.
For agent-guided mapping (matching your own data model to Olira's) or anything
that needs the current, authoritative catalog — including each type's full payload
JSON Schema — call the live catalog instead. Requires `sdk:event-log` scope.

```python
# List every log type in the platform catalog
for lt in olira.list_log_types():
    print(lt.subtype, lt.display_name, lt.payload_schema)

# Look up one type by subtype (or a known deprecated alias)
lt = olira.get_log_type(subtype="mood_report")
print(lt.payload_schema)
```

`list_log_types()` returns `list[LogType]`; `get_log_type()` returns a single `LogType`.
Both raise `ValidationError`-style 404s (via `OliraError`) for an unknown subtype.

**`LogType` fields:** `subtype`, `category`, `aliases`, `display_name`, `description`,
`payload_schema` (JSON Schema dict), `payload_description`, `sources`, `version`.

## Patients

All patient functions require an API key with `api:manage-patients` scope.

> **Project scoping:** patients belong to a single project, stamped at creation from the client's selected workspace. Point the client at a project with `OliraClient(project=...)` / `olira.init(project=...)` and `create_patient()` lands there, while `list_patients()` returns only that project's patients. Omit `project` and a project-locked key uses its own project; an org-wide key uses the org's default project. A patient created in one project is invisible to others. See [Projects](#projects) and [Selecting a project](#selecting-a-project-workspace).

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
list_patients(*, limit: int = 100, offset: int = 0, external_system: str | None = None, external_value: str | None = None, integration_id: str | None = None) -> PatientListResult
```

List patients in your organisation. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope.

Filters compose as AND on the **same** identifier: `external_system` alone finds every
patient with an identifier for that system (e.g. every Epic patient);
`external_system` + `external_value` finds the one patient with that exact identifier;
`integration_id` alone finds every patient linked to that specific integration instance.
`external_value` requires `external_system`.

| Parameter         | Required | Type            | Default |
| ----------------- | -------- | --------------- | ------- |
| `limit`           | No       | `int`           | `100`   |
| `offset`          | No       | `int`           | `0`     |
| `external_system` | No       | `Optional[str]` | `None`  |
| `external_value`  | No       | `Optional[str]` | `None`  |
| `integration_id`  | No       | `Optional[str]` | `None`  |

**Example:**

```python
result = olira.list_patients(limit=20, offset=0)
for patient in result.patients:
    print(patient.id, patient.first_name, patient.last_name)

# Every patient with an Epic identifier, without knowing the FHIR id:
epic_patients = olira.list_patients(external_system="epic")

# Every patient linked to one Epic instance:
linked = olira.list_patients(integration_id="66f0a1...")
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

`external_identifiers` is **merge/append-only**: any `(system, value)` pair not already
stored is added, and anything already stored — including an identifier a platform
integration owns — is left untouched, whether or not you include it in the list. An
empty list is rejected (422); use [`remove_patient_external_identifiers`](#remove_patient_external_identifiers)
to remove one.

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

Link a patient to their ID in another system using `ExternalIdentifier`. On `update_patient`,
new identifiers are **added**, not swapped in — this call attaches two identifiers to a
patient that has none yet:

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

> **Identifier uniqueness is per project, and a plain SDK id shares a namespace with
> integration-owned ids of the same `(system, value)`.** Identifiers created by an
> integration sync carry that instance's id. Identifiers you supply through the SDK
> (your CRM id, an SSN) have `integration_id: None`. Two Epic *instances* may share a
> value — Hospital A and Hospital B can both use the same FHIR id. But an SDK-supplied
> `("epic", "MRN-12345")` **does** conflict with an integration-owned
> `("epic", "MRN-12345")` on another patient in the same project (409). That stops a
> roster patient and an SDK patient from splitting the same chart. Duplicate checks do
> not cross projects. See [Integrations & Instances](#integrations--instances).

**`ExternalIdentifier.integration_id`** is the platform-assigned id of the integration that
owns an identifier (e.g. an Epic sync). It's read-only — Olira sets it, never you — and is
`None` for identifiers you supply yourself. It's included on every `get_patient()` /
`list_patients()` response. You never need to set it: `update_patient()` never clears a
stored `integration_id`, whether you omit the identifier entirely or echo it back without
the field. Its main use is telling you what removing an identifier will *do*: any
identifier can be removed via `remove_patient_external_identifiers()` regardless of
`integration_id`, but removing one that's non-`None` unlinks the patient from that
integration — see [`remove_patient_external_identifiers`](#remove_patient_external_identifiers)
for the full flow.

> **Don't hand-roll a GET → append → PUT.** If you only want to attach your own identifier
> to a patient — without reading back and re-sending every identifier it already has —
> use `add_patient_external_identifiers()` below instead of reconstructing the full list
> yourself:
>
> ```python
> # ✅ Direct — adds one identifier, leaves everything else untouched.
> olira.add_patient_external_identifiers(
>     patient_id="patient-uuid",
>     identifiers=[ExternalIdentifier(system="my-crm", value="CRM-4471")],
> )
> ```

#### `add_patient_external_identifiers`

```python
add_patient_external_identifiers(*, patient_id: str, identifiers: list[ExternalIdentifier]) -> ExternalIdentifierMutationResult
```

Add one or more external identifiers to a patient. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope. Idempotent — an identifier already
present (matched on `system` + `value`) is skipped, not modified. Only `system` and `value`
are sent; `integration_id` is platform-owned and stripped even if set on the objects you
pass in — you cannot use this call to claim ownership of an identifier on behalf of an
integration.

| Parameter     | Required | Type                       | Default |
| ------------- | -------- | --------------------------- | ------- |
| `patient_id`  | Yes      | `str`                       | —       |
| `identifiers` | Yes      | `list[ExternalIdentifier]`  | —       |

**Example:**

```python
result = olira.add_patient_external_identifiers(
    patient_id="patient-uuid",
    identifiers=[ExternalIdentifier(system="my-crm", value="CRM-4471")],
)
print(result.added, result.skipped)
```

#### `remove_patient_external_identifiers`

```python
remove_patient_external_identifiers(*, patient_id: str, identifiers: list[ExternalIdentifierMatcher]) -> ExternalIdentifierMutationResult
```

Remove one or more external identifiers from a patient. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope. This is the **only** way to remove
an external identifier — `update_patient()` never removes. Each entry is a
[`ExternalIdentifierMatcher`](#externalidentifiermatcher), not a full identifier: rows
are removed if they match every field you set.

- `system` + `value` — exactly one identifier (the common case).
- `system` only — every identifier for that system. `system="epic"` unlinks the
  patient from **every** connected Epic instance; use `integration_id` alone to drop
  one hospital.
- `integration_id` only — every identifier owned by that specific integration instance.
- `system` + `integration_id` — that system on that instance only.

It can match **any** identifier, including one owned by a platform integration: doing so
is a deliberate, irreversible unlink. Under `linked_only` import mode, the patient
immediately stops receiving further data from that integration. Idempotent — a matcher
that matches nothing is skipped, not an error. `value` without `system` is rejected.

> **How to find the identifier you're about to delete — and know what removing it does.**
> Call `get_patient` first. Check `integration_id` for the **consequence**, not for
> permission: `None` means you supplied the identifier yourself. A non-`None` value
> means an EHR integration owns it — removing it unlinks the patient from that
> integration. If you want the human-readable name of that integration, resolve it
> with `GET /v1/integrations/{integration_id}` (`sdk:integrations` scope) — that's a
> different API surface than patient management and isn't exposed by this SDK version.
>
> ```python
> from olira import ExternalIdentifierMatcher
>
> patient = olira.get_patient(patient_id="patient-uuid")
> for ident in patient.external_identifiers:
>     print(ident.system, ident.value, "owned by integration:", ident.integration_id)
> # epic       MRN-12345   owned by integration: 66f0a1...   ← a platform integration link
> # my-crm     CRM-4471    owned by integration: None        ← yours
>
> # Remove the identifier you added yourself:
> olira.remove_patient_external_identifiers(
>     patient_id="patient-uuid",
>     identifiers=[ExternalIdentifierMatcher(system="my-crm", value="CRM-4471")],
> )
>
> # Drop this patient from one Epic instance (leave other hospitals and your ids):
> olira.remove_patient_external_identifiers(
>     patient_id="patient-uuid",
>     identifiers=[ExternalIdentifierMatcher(integration_id="66f0a1...")],
> )
> ```

| Parameter     | Required | Type                              | Default |
| ------------- | -------- | --------------------------------- | ------- |
| `patient_id`  | Yes      | `str`                             | —       |
| `identifiers` | Yes      | `list[ExternalIdentifierMatcher]` | —       |

**Example:**

```python
from olira import ExternalIdentifierMatcher

result = olira.remove_patient_external_identifiers(
    patient_id="patient-uuid",
    identifiers=[ExternalIdentifierMatcher(system="my-crm", value="CRM-4471")],
)
print(result.removed, result.skipped)
```

#### `ExternalIdentifierMutationResult`

| Field                   | Type                       | Notes                                          |
| ----------------------- | -------------------------- | ----------------------------------------------- |
| `patient_id`            | `str`                       |                                                  |
| `added`                 | `int`                       | Defaults to `0`                                 |
| `removed`               | `int`                       | Defaults to `0`                                 |
| `skipped`               | `int`                       | Already present (add) or matchers that hit nothing (remove) |
| `external_identifiers`  | `list[ExternalIdentifier]`  | Full list after the mutation                    |

### Delete a patient

#### `delete_patient`

```python
delete_patient(*, patient_id: str, permanent: bool = False) -> None
```

Delete a patient. Module-level proxy to the singleton client.

Requires an API key with the api:manage-patients scope.

| Parameter    | Required | Type   | Default |
| ------------ | -------- | ------ | ------- |
| `patient_id` | Yes      | `str`  | —       |
| `permanent`  | No       | `bool` | `False` |

Soft-deletes by default (sets `status=deleted`; the record and all associated logs/state
are retained for audit purposes). Pass `permanent=True` to **hard-delete** the patient and
cascade-delete every associated document — event logs, state, conversations, notes,
symptoms, memories, etc. **Irreversible.**

Use `permanent=True` to clean up a duplicate or erroneously-created patient — e.g. one
whose external identifier collides with another patient's (see
[Integrations & Instances](#integrations--instances) for how identifiers are
scoped per integration instance). Soft-deleting is enough to free up the identifier for
reuse (duplicate checks skip `status=deleted` patients), but its logs stick around until
you hard-delete it.

```python
# Stop a duplicate from causing further confusion, keep it for now:
olira.delete_patient(patient_id=duplicate_id)

# Once you're sure it's a true duplicate, purge everything tied to it:
olira.delete_patient(patient_id=duplicate_id, permanent=True)
```

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

result = olira.create_patients_batch(
    [
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
    ]
)
print(f"Created {result.count}, errors: {len(result.errors)}")
```

### Patient response models

### `ExternalIdentifier`

Links a patient to their ID in an external system (e.g. Epic MRN, Flatiron ID, FHIR resource ID).

| Field            | Required | Type            | Description                                                                 |
| ---------------- | -------- | --------------- | ---------------------------------------------------------------------------- |
| `system`         | Yes      | `str`           | System name, e.g. 'epic', 'flatiron', 'fhir'                                 |
| `value`          | Yes      | `str`           | Patient ID in that system                                                     |
| `integration_id` | No       | `Optional[str]` | Read-only. Platform-assigned id of the owning integration; `None` if you supplied the identifier yourself. |

### `ExternalIdentifierMatcher`

Selects one or more stored identifiers to remove. Every field is optional; rows match if they satisfy every field you set. At least one field is required. `value` without `system` is rejected.

| Field            | Required | Type            | Description |
| ---------------- | -------- | --------------- | ----------- |
| `system`         | No       | `Optional[str]` | System name. Alone: every identifier for that system. `system="epic"` unlinks every connected Epic instance. |
| `value`          | No       | `Optional[str]` | Value. Requires `system`. With `system`: exactly one identifier. |
| `integration_id` | No       | `Optional[str]` | Integration instance id. Alone: every identifier owned by that instance. With `system`: that system on that instance only. |

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
| `external_identifiers` | No       | `Optional[list[ExternalIdentifier]]` | Merge/append-only — see [External Identifiers](#external-identifiers). An empty list is rejected. |
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

## Projects

All project functions require an API key with the **`api:manage-projects`** scope **and an org-wide key** (a project-locked key is confined to its own workspace and gets 403 on these routes).

A **project** is a self-contained, isolated workspace within your organisation — its own patients, event logs, patient state, views, cohorts, and platform configuration. Every organisation has exactly one **default** project; data written without a selected project lands there when using an org-wide key (a project-locked key with no selection writes to its own project instead). Everything you can do with projects in the Olira Console is available here. To operate _inside_ a project (create patients, send logs, read state), select it at init via [`project=`](#selecting-a-project-workspace) rather than through these management calls.

The lifecycle mirrors the Console exactly: **create** (or **duplicate**) → active → **rename** / **deprecate** (soft-delete, reversible) → **restore**, and finally **permanent delete** (only from the deprecated state, irreversible).

See the full runnable walkthrough in [`examples/10_project_management.py`](examples/10_project_management.py).

---

### `create_project`

```python
project = client.create_project(name="Dev Sandbox", slug="dev-sandbox", environment="dev")
# module-level: olira.create_project(name=..., slug=..., description=..., environment=...)
```

Creates a new **empty** project — fresh configuration, no patients or data carried over.

**Parameters**

| Name          | Type          | Required | Description                                                                                                                                                                                   |
| ------------- | ------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`        | `str`         | Yes      | Display name. Must be unique per org (1–100 chars).                                                                                                                                           |
| `slug`        | `str \| None` | No       | The handle you later pass to `init(project=...)` / `X-Olira-Project`. Unique per org, normalized server-side (lowercased, non-alphanumerics → hyphens); **derived from `name` when omitted**. |
| `description` | `str \| None` | No       | Optional free-text description.                                                                                                                                                               |
| `environment` | `str \| None` | No       | Optional intent tag: `"dev"`, `"staging"`, or `"prod"`.                                                                                                                                       |

**Returns** `Project`.

---

### `list_projects`

```python
result = client.list_projects()
for p in result.data:
    print(p.slug, p.status, p.is_default)
```

**Returns** `ProjectListResult` — `data: list[Project]` (active first, default first).

---

### `get_project`

```python
project = client.get_project(project="dev-sandbox")  # id or slug
```

**Parameters**

| Name      | Type  | Required | Description         |
| --------- | ----- | -------- | ------------------- |
| `project` | `str` | Yes      | Project id or slug. |

**Returns** `Project`.

---

### `duplicate_project`

```python
prod = client.duplicate_project(project="dev-sandbox", name="Prod", slug="prod", environment="prod")
```

Creates a new project seeded from an existing one's **configuration only** — platform config (event types, connections), population-view pipeline templates, and cohort _definitions_ (with empty rosters). Patients, event logs, patient state, and view results are **never** copied; the duplicate starts empty. This is the dev→prod handoff: validate a setup in a dev project, then duplicate it into production rather than rebuilding by hand.

**Parameters**

| Name          | Type          | Required | Description                                                                                                                                                                             |
| ------------- | ------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `project`     | `str`         | Yes      | Source project id or slug to copy configuration from.                                                                                                                                   |
| `name`        | `str`         | Yes      | Name for the new project. Must be unique per org.                                                                                                                                       |
| `slug`        | `str \| None` | No       | The new project's handle for `init(project=...)`. Unique per org, normalized server-side; derived from `name` when omitted — pass a distinct one so it doesn't collide with the source. |
| `description` | `str \| None` | No       | Optional description for the new project.                                                                                                                                               |
| `environment` | `str \| None` | No       | Optional intent tag for the new project.                                                                                                                                                |

**Returns** `Project` (the new project).

---

### `rename_project`

```python
project = client.rename_project(project="dev-sandbox", name="Dev Sandbox 2")
```

Rename a project or update its description / environment tag. `project` is the id or slug; only supplied fields change.

**Parameters**

| Name          | Type          | Required | Description                        |
| ------------- | ------------- | -------- | ---------------------------------- |
| `project`     | `str`         | Yes      | Project id or slug.                |
| `name`        | `str \| None` | No       | New display name (unique per org). |
| `description` | `str \| None` | No       | New description.                   |
| `environment` | `str \| None` | No       | New environment tag.               |

**Returns** `Project`.

---

### `deprecate_project`

```python
project = client.deprecate_project(project="dev-sandbox")
print(project.status)  # "deprecated"
```

Soft-delete: moves the project to the deprecated list. Its data becomes unreachable through normal reads but is fully retained — **reversible** via `restore_project`.

**Guards:** the default project and the org's _last active_ project cannot be deprecated (400).

**Parameters**

| Name      | Type  | Required | Description         |
| --------- | ----- | -------- | ------------------- |
| `project` | `str` | Yes      | Project id or slug. |

**Returns** `Project`.

---

### `restore_project`

```python
project = client.restore_project(project="dev-sandbox")
print(project.status)  # "active"
```

Reactivate a deprecated project, fully intact.

**Parameters**

| Name      | Type  | Required | Description         |
| --------- | ----- | -------- | ------------------- |
| `project` | `str` | Yes      | Project id or slug. |

**Returns** `Project`.

---

### `delete_project`

```python
client.deprecate_project(project="dev-sandbox")  # must be deprecated first
client.delete_project(project="dev-sandbox")  # permanent, no recovery
```

Permanently delete a **deprecated** project and its scoped configuration (cohorts, view templates, pipelines, config). **Irreversible.**

**Guards:** the project must already be deprecated, and deletion is **blocked (409) while it still has patients** — delete or export them first. The default project can never be deleted.

**Parameters**

| Name      | Type  | Required | Description         |
| --------- | ----- | -------- | ------------------- |
| `project` | `str` | Yes      | Project id or slug. |

**Returns** `None`.

---

### `Project`

| Field           | Type          | Description                                                                 |
| --------------- | ------------- | --------------------------------------------------------------------------- |
| `id`            | `str`         | Olira-assigned project id.                                                  |
| `name`          | `str`         | Display name.                                                               |
| `slug`          | `str`         | URL-friendly identifier, unique per org. Usable anywhere an id is accepted. |
| `description`   | `str \| None` | Free-text description.                                                      |
| `environment`   | `str \| None` | Intent tag: `dev` / `staging` / `prod`.                                     |
| `status`        | `str`         | `active` or `deprecated`.                                                   |
| `is_default`    | `bool`        | Whether this is the org's default project.                                  |
| `created_at`    | `str \| None` | Creation timestamp (ISO 8601 string).                                       |
| `deprecated_at` | `str \| None` | When it was deprecated (ISO 8601 string), if applicable.                    |

`ProjectListResult` — `data: list[Project]`.

---

## Cohorts

All cohort functions require an API key with `api:manage-patients` scope.

> **Project scoping:** cohorts live _inside_ a project. Select the workspace at init (`OliraClient(project=...)` / `olira.init(project=...)`); every cohort call then reads and writes within that project. Omit `project` and a project-locked key uses its own project; an org-wide key uses the org's default project. See [Projects](#projects).

Cohorts are named patient groups scoped to your organisation. Use them to assign summary types to a defined set of patients without touching individual records. Template assignments cascade to patients when they are added to a cohort, and to all existing cohort members when a template is assigned.

---

### `create_cohort`

```python
cohort = client.create_cohort(name="High-Risk Patients", description="Weekly review")
# module-level: olira.create_cohort(name=..., description=...)
```

**Parameters**

| Name          | Type          | Required | Description                                                  |
| ------------- | ------------- | -------- | ------------------------------------------------------------ |
| `name`        | `str`         | Yes      | Display name. Must be unique per organisation (1–200 chars). |
| `description` | `str \| None` | No       | Optional free-text description.                              |

**Returns** `Cohort` — `id`, `name`, `description`, `patient_ids`, `created_at`, `updated_at`.

---

### `list_cohorts`

```python
result = client.list_cohorts()
for c in result.data:
    print(c.id, c.name, c.patient_count, c.template_assignment_count)
```

**Returns** `CohortListResult` — `data: list[CohortListItem]`.

`CohortListItem` fields: `id`, `name`, `description`, `patient_count`, `template_assignment_count`, `created_at`, `updated_at`.

---

### `get_cohort`

```python
cohort = client.get_cohort(cohort_id="...")
print(cohort.patient_ids)
```

**Parameters**

| Name        | Type  | Required | Description               |
| ----------- | ----- | -------- | ------------------------- |
| `cohort_id` | `str` | Yes      | Olira-assigned cohort id. |

**Returns** `Cohort` including the full `patient_ids` list.

---

### `update_cohort`

```python
cohort = client.update_cohort(cohort_id="...", description="New description")
```

**Parameters**

| Name          | Type          | Required | Description                               |
| ------------- | ------------- | -------- | ----------------------------------------- |
| `cohort_id`   | `str`         | Yes      | Olira-assigned cohort id.                 |
| `name`        | `str \| None` | No       | New display name. Must be unique per org. |
| `description` | `str \| None` | No       | New description.                          |

Only supplied fields are changed. **Returns** `Cohort`.

---

### `delete_cohort`

```python
result = client.delete_cohort(cohort_id="...")
print(result.deleted)  # True
```

Permanently deletes the cohort and all its template assignments. Patient records are not affected.

**Parameters**

| Name        | Type  | Required | Description               |
| ----------- | ----- | -------- | ------------------------- |
| `cohort_id` | `str` | Yes      | Olira-assigned cohort id. |

**Returns** `CohortDeleteResult` — `deleted: bool`, `cohort_id: str`.

---

### `add_patients_to_cohort`

```python
result = client.add_patients_to_cohort(cohort_id="...", patient_ids=["pid1", "pid2"])
print(result.patient_count)  # total enrolled after operation
```

Idempotent — patients already in the cohort are silently skipped. Max 500 per call.

**Parameters**

| Name          | Type        | Required | Description                           |
| ------------- | ----------- | -------- | ------------------------------------- |
| `cohort_id`   | `str`       | Yes      | Olira-assigned cohort id.             |
| `patient_ids` | `list[str]` | Yes      | Olira patient ids to enrol (max 500). |

**Returns** `CohortPatientMutationResult` — `cohort_id`, `patient_count`.

---

### `remove_patients_from_cohort`

```python
result = client.remove_patients_from_cohort(cohort_id="...", patient_ids=["pid1"])
print(result.patient_count)  # total enrolled after operation
```

Max 500 per call. Patient records are not affected.

**Parameters**

| Name          | Type        | Required | Description                            |
| ------------- | ----------- | -------- | -------------------------------------- |
| `cohort_id`   | `str`       | Yes      | Olira-assigned cohort id.              |
| `patient_ids` | `list[str]` | Yes      | Olira patient ids to remove (max 500). |

**Returns** `CohortPatientMutationResult`.

---

### `assign_cohort_template`

```python
assignment = client.assign_cohort_template(cohort_id="...", summary_type="symptom_overview")
print(assignment.template_id)
```

Assigns a summary type to the cohort. Snapshot documents for existing cohort patients are seeded in the background.

**Parameters**

| Name           | Type  | Required | Description                                  |
| -------------- | ----- | -------- | -------------------------------------------- |
| `cohort_id`    | `str` | Yes      | Olira-assigned cohort id.                    |
| `summary_type` | `str` | Yes      | Summary type slug (e.g. `symptom_overview`). |

**Returns** `CohortTemplateAssignment` — `id`, `summary_type`, `template_id`, `cohort_id`, `assigned_at`.

---

### `unassign_cohort_template`

```python
result = client.unassign_cohort_template(cohort_id="...", summary_type="symptom_overview")
print(result["deleted"])  # True
```

**Parameters**

| Name           | Type  | Required | Description                  |
| -------------- | ----- | -------- | ---------------------------- |
| `cohort_id`    | `str` | Yes      | Olira-assigned cohort id.    |
| `summary_type` | `str` | Yes      | Summary type slug to remove. |

**Returns** `dict` — `{"deleted": True}`.

---

### `list_cohort_templates`

```python
result = client.list_cohort_templates(cohort_id="...")
for t in result.data:
    print(t.summary_type, t.assigned_at)
```

**Parameters**

| Name        | Type  | Required | Description               |
| ----------- | ----- | -------- | ------------------------- |
| `cohort_id` | `str` | Yes      | Olira-assigned cohort id. |

**Returns** `CohortTemplatesResult` — `data: list[CohortTemplateAssignment]`.

---

### Cohort response models

| Model                         | Fields                                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- |
| `Cohort`                      | `id`, `name`, `description`, `patient_ids`, `created_at`, `updated_at`                                |
| `CohortListItem`              | `id`, `name`, `description`, `patient_count`, `template_assignment_count`, `created_at`, `updated_at` |
| `CohortListResult`            | `data: list[CohortListItem]`                                                                          |
| `CohortPatientMutationResult` | `cohort_id`, `patient_count`                                                                          |
| `CohortTemplateAssignment`    | `id`, `summary_type`, `template_id`, `cohort_id`, `assigned_at`                                       |
| `CohortTemplatesResult`       | `data: list[CohortTemplateAssignment]`                                                                |
| `CohortDeleteResult`          | `deleted`, `cohort_id`                                                                                |

---

## Schemas

All schema-management functions require an API key with `api:org-config` scope.

Register your own event subtypes (e.g. `myorg_widget_reading`) and their translation into Olira's platform catalog, without going through Slack. Registering always lands as a **pending request** — Olira reviews and materializes the real schema + mapping before it can be activated, so a client (or their own agent) can submit and inspect requests while Olira retains authorship of the mapping logic. Versioning is presented as **one number per subtype**: every change moves the schema and the mapping together.

---

### `register_schema`

```python
registration = client.register_schema(
    subtype="widget_ping",
    description="Widget sensor ping events",
    input_examples=[{"reading_value": 42, "unit": "lux"}],
)
# module-level: olira.register_schema(subtype=..., description=..., input_examples=..., schema=..., mapping=...)
```

Pass both `schema` and `mapping` for a "full_spec" submission (e.g. your own agent already authored them); pass neither/either for an "assisted" submission Olira will author from your `input_examples` + `description`. Always lands as a pending request — it never auto-activates.

**Parameters**

| Name             | Type                 | Required | Description                                                                                                |
| ---------------- | -------------------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| `subtype`        | `str`                | Yes      | New org-defined source event subtype, e.g. `rc_conversation_completed` (lowercase snake_case, 3–64 chars). |
| `description`    | `str`                | No       | What this source event represents.                                                                         |
| `input_examples` | `list[dict] \| None` | No       | Sample raw payloads (capped at 20).                                                                        |
| `schema`         | `dict \| None`       | No       | Full JSON Schema for the payload, if already authored.                                                     |
| `mapping`        | `dict \| None`       | No       | Full mapping spec (`source_root`/`targets`/`unmapped_fields_policy`), if already authored.                 |

**Returns** `SchemaRegistrationResult` — `registration_id`, `subtype`, `target_version`, `submission_mode` (`"full_spec"` or `"assisted"`), `status` (always `"pending_review"`), `self_check`.

---

### `list_schemas`

```python
for summary in client.list_schemas():
    print(summary.subtype, summary.status, summary.active_version)
```

**Returns** `list[SchemaSummary]` — each with `subtype`, `status` (`"pending"`, `"active"`, or `"deprecated"`), `active_version`, `latest_version`, `description`.

---

### `get_schema`

```python
detail = client.get_schema(subtype="widget_ping")
for v in detail.versions:
    print(v.version, v.status, v.source)
```

**Parameters**

| Name      | Type  | Required | Description                    |
| --------- | ----- | -------- | ------------------------------ |
| `subtype` | `str` | Yes      | Org-native subtype to look up. |

**Returns** `SchemaDetail` — `subtype`, `status`, `active_version`, `versions: list[SchemaVersion]`. Each `SchemaVersion` has `version`, `status`, `source` (`"registration"` if not yet materialized, else `"materialized"`), `payload_schema`, `mapping_summary`, `description`, `created_at`, `created_by`, `submission_mode`, `self_check`, `registration_id`.

---

### `check_schema`

```python
result = client.check_schema(
    examples=[{"reading_value": 42, "unit": "lux"}],
    schema={"type": "object", "required": ["reading_value"], "properties": {"reading_value": {"type": "number"}}},
    mapping={
        "targets": [
            {"target_subtype": "heart_rate_data", "field_mappings": [{"target": "avg_bpm", "source": "reading_value"}]}
        ]
    },
)
print(result.ok)
```

Dry-runs a schema/mapping over sample payloads — no writes. Runs the same org gate, pure mapping engine, and platform-catalog gate the live ingest route uses, so a green check genuinely predicts what logging would accept. Pass `subtype` (optionally with `version`) to check a stored or still-pending spec instead of an inline `schema`/`mapping`.

**Parameters**

| Name       | Type           | Required | Description                                                                            |
| ---------- | -------------- | -------- | -------------------------------------------------------------------------------------- |
| `examples` | `list[dict]`   | Yes      | Sample payloads to run through.                                                        |
| `subtype`  | `str \| None`  | No       | Load the active (or pinned `version`) schema/mapping for this subtype as the baseline. |
| `version`  | `int \| None`  | No       | Pin a specific version instead of the active one.                                      |
| `schema`   | `dict \| None` | No       | Inline schema, overriding or replacing the stored one.                                 |
| `mapping`  | `dict \| None` | No       | Inline mapping, overriding or replacing the stored one.                                |

**Returns** `SchemaCheckResult` — `ok`, `results: list[SchemaCheckExampleResult]` (each with `input`, `ok`, `mapped_events`, `errors`), `error`.

---

### `edit_schema`

```python
edited = client.edit_schema(subtype="widget_ping", description="Updated description")
print(edited.target_version)
```

Proposes a schema/mapping change. Always opens a new pending request targeting the next version — never mutates an active version in place. Editing an already-active subtype defaults any field you omit to what's currently active, so the reviewer sees a complete proposed spec even from a partial edit.

**Parameters**

| Name             | Type                 | Required | Description                       |
| ---------------- | -------------------- | -------- | --------------------------------- |
| `subtype`        | `str`                | Yes      | Subtype to propose a change for.  |
| `description`    | `str \| None`        | No       | New description, if changing it.  |
| `input_examples` | `list[dict] \| None` | No       | Replacement sample payloads.      |
| `schema`         | `dict \| None`       | No       | New JSON Schema, if changing it.  |
| `mapping`        | `dict \| None`       | No       | New mapping spec, if changing it. |

**Returns** `SchemaRegistrationResult`.

---

### `deprecate_schema`

```python
result = client.deprecate_schema(subtype="widget_ping")
print(result.status)  # "deprecated"
```

Deprecates a materialized version (default: the active one), or withdraws a still-pending request if nothing has been materialized yet. Never a hard delete.

**Parameters**

| Name      | Type          | Required | Description                                                            |
| --------- | ------------- | -------- | ---------------------------------------------------------------------- |
| `subtype` | `str`         | Yes      | Subtype to deprecate.                                                  |
| `version` | `int \| None` | No       | Specific version to archive. Defaults to the currently active version. |

**Returns** `SchemaActionResult` — `subtype`, `version`, `status`.

---

### `activate_schema_version`

```python
result = client.activate_schema_version(subtype="widget_ping", version=1)
print(result.status)  # "active"
```

Activates an already-materialized version, archiving whichever version was previously active. Re-runs `check_schema` against the type definition's `sample_payload` first and refuses to activate a version that fails it.

**Parameters**

| Name      | Type  | Required | Description                                                                           |
| --------- | ----- | -------- | ------------------------------------------------------------------------------------- |
| `subtype` | `str` | Yes      | Subtype to activate a version for.                                                    |
| `version` | `int` | Yes      | Version to activate. Must already be materialized (schema and mapping both authored). |

**Returns** `SchemaActionResult`.

---

### Schema response models

| Model                      | Fields                                                                                                                                                            |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SchemaRegistrationResult` | `registration_id`, `subtype`, `target_version`, `submission_mode`, `status`, `self_check`                                                                         |
| `SchemaSummary`            | `subtype`, `status`, `active_version`, `latest_version`, `description`                                                                                            |
| `SchemaDetail`             | `subtype`, `status`, `active_version`, `versions: list[SchemaVersion]`                                                                                            |
| `SchemaVersion`            | `version`, `status`, `source`, `payload_schema`, `mapping_summary`, `description`, `created_at`, `created_by`, `submission_mode`, `self_check`, `registration_id` |
| `SchemaCheckResult`        | `ok`, `results: list[SchemaCheckExampleResult]`, `error`                                                                                                          |
| `SchemaCheckExampleResult` | `input`, `ok`, `mapped_events`, `errors`                                                                                                                          |
| `SchemaActionResult`       | `subtype`, `version`, `status`                                                                                                                                    |

---

## Logs

All log functions require `sdk:event-log` scope.

> **Project scoping:** logs inherit their patient's project automatically — you never pass a project when logging. Just target a patient that lives in the workspace you want (select it at init with `OliraClient(project=...)` / `olira.init(project=...)`), and the log is denormalised into that same project. Reads (`get_logs()`, `logs()`, `population_logs()`) are likewise confined to the selected project. See [Projects](#projects).

Use `log()` and `log_batch()` for **ongoing operational traffic**—applications, integrations, and moderate batch sizes where each submission should update patient state through Olira's immediate graph-update path.

Use `log_fhir()` when your source data is already in **FHIR R4 format**. Olira maps the resource to one or more platform log types via the same absorber used by Epic/Cerner integrations, so you don't need to choose a `log_type` or build Olira-shaped payloads yourself. Pass `idempotency_key` on `log_batch()` / `log_fhir()` if you might retry the call.

For **bulk historical data** (e.g. months or years at once, or onboarding backfills before go-live), use **[Historical Data Ingestion](#historical-data-ingestion)** with `create_ingestion_job()` and the **`sdk:historical-ingest`** scope. That pipeline stages rows, replays them in chronological order, and backfills summary views — not `log_batch` at volume.

### Log a single event

#### `log`

```python
log(*, log_type: OliraLogType, patient_id: str, payload: dict[str, Any] | None = None, trace: OliraTrace | None = None, timestamp: str | None = None, metadata: dict[str, Any] | None = None, write_back: bool = False, write_back_integration_id: str | None = None) -> None
```

Enqueue an event for background delivery. Module-level proxy to the singleton client.

| Parameter                   | Required | Type                       | Default |
| --------------------------- | -------- | -------------------------- | ------- |
| `log_type`                  | Yes      | `OliraLogType`             | —       |
| `patient_id`                | Yes      | `str`                      | —       |
| `payload`                   | No       | `Optional[dict[str, Any]]` | `None`  |
| `trace`                     | No       | `Optional[OliraTrace]`     | `None`  |
| `timestamp`                 | No       | `Optional[str]`            | `None`  |
| `metadata`                  | No       | `Optional[dict[str, Any]]` | `None`  |
| `write_back`                | No       | `bool`                     | `False` |
| `write_back_integration_id` | No       | `Optional[str]`            | `None`  |

`write_back=True` requests that this log also be **written back into the org's connected
system** (e.g. a vitals reading pushed into Epic as an `Observation`). It is a request, not a
grant: the write fires only when the API key carries the `sdk:integration-write` scope AND
Olira has write-configured the integration for this `log_type` — otherwise it is a silent
no-op and the log ingests normally either way.

An organization may hold **several integrations of the same type** (e.g. Epic for
Hospital A and Hospital B). With a single write-configured integration the target is
inferred; otherwise the patient's integration-linked identifiers disambiguate, and
`write_back_integration_id` (the integration's id from `GET /v1/integrations`) settles
ties explicitly — see [Integrations & Instances](#integrations--instances).

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

result = olira.log_batch(
    [
        LogSpec(
            log_type=OliraLogType.VITALS_MEASUREMENT,
            patient_id="patient-uuid",
            payload={
                "measurements": {
                    "systolic_bp_mmhg": 128,
                    "diastolic_bp_mmhg": 82,
                    "heart_rate_bpm": 72,
                    "spo2_percent": None,
                    "weight_kg": None,
                    "temperature_celsius": None,
                    "respiratory_rate_bpm": None,
                },
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
    ]
)
print(f"Accepted: {result.accepted}, Failed: {result.failed}")
```

### Log a FHIR resource

#### `log_fhir`

```python
log_fhir(*, patient_id: str, resource: dict[str, Any], idempotency_key: str | None = None) -> BatchResult
```

Submit a single FHIR R4 resource for immediate ingestion. Module-level proxy to the singleton client.

Olira maps the resource to one or more platform log types via the FHIR absorber (the same schema mapper used by Epic/Cerner integrations) and processes each resulting event immediately for the patient. You do not choose `log_type` or build Olira-shaped payloads — the absorber handles the mapping.

Requires `sdk:event-log` scope.

| Parameter         | Required | Type             | Default |
| ----------------- | -------- | ---------------- | ------- |
| `patient_id`       | Yes      | `str`            | —       |
| `resource`         | Yes      | `dict[str, Any]` | —       |
| `idempotency_key`  | No       | `Optional[str]`  | `None`  |

`resource` must be a valid FHIR R4 JSON object with a `resourceType` field. Supported types include `Condition`, `MedicationRequest`, `MedicationStatement`, `MedicationAdministration`, `AllergyIntolerance`, `Appointment`, `Encounter`, `Procedure`, `Immunization`, `DiagnosticReport`, `DocumentReference`, `CarePlan`, `CareTeam`, `FamilyMemberHistory`, `Goal`, `Observation` (vital-signs), and `Patient`.

`idempotency_key` makes a retry after a network error or 5xx safe: send the same key and the same resource again and Olira will not create a second event. Pass a key whenever you plan to retry — without one, `log_fhir()` does not reliably treat a resend as a duplicate. If the FHIR resource has no date the absorber can use, Olira timestamps the event at processing time, so two calls without a key are stored separately. Because of this, the SDK's own transport does not automatically retry a `log_fhir()` call on a network error or 5xx unless you pass `idempotency_key` — without one, an automatic retry could itself create the duplicate this parameter exists to prevent.

One FHIR resource can map to several Olira events. For example, a treatment plan from an EHR can produce both a follow-up item and a treatment-phase update. Pass **one** key for the call; do not add a log type or a key per event. Olira records `your-key:clinical_plan_item` and `your-key:treatment_phase` internally so each mapped event can be retried on its own. A patient demographics update is recorded as `your-key:demographics`. `log_batch()` keeps the key you send unchanged, so the same string on both methods does not collide.

**Raises `ValidationError`** if:

- `resourceType` is missing (HTTP 422 from the API)
- The resource maps to zero Olira events — unsupported type, unrecognized fields, or (for `Observation`) unrecognized category/LOINC code. The exception message explains why.

**Example — safe retry:**

```python
import olira

olira.init(api_key="YOUR_API_KEY")

resource = {
    "resourceType": "Condition",
    "id": "condition-1",
    "code": {"coding": [{"system": "http://snomed.info/sct", "code": "254837009"}]},
    "subject": {"reference": "Patient/example"},
}

# If this call's response is lost to a network error, retry it verbatim —
# the same idempotency_key guarantees no duplicate event is created.
result = olira.log_fhir(patient_id="patient-uuid", resource=resource, idempotency_key="condition-2026-01-10")
```

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
    idempotency_key="condition-2026-01-10",
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

| Field                       | Required | Type                       | Description                                                                                                                               |
| --------------------------- | -------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `log_type`                  | Yes      | `OliraLogType`             | —                                                                                                                                         |
| `patient_id`                | Yes      | `str`                      | —                                                                                                                                         |
| `payload`                   | No       | `Optional[dict[str, Any]]` | — (default: `None`)                                                                                                                       |
| `trace`                     | No       | `Optional[OliraTrace]`     | — (default: `None`)                                                                                                                       |
| `timestamp`                 | No       | `Optional[str]`            | — (default: `None`)                                                                                                                       |
| `idempotency_key`           | No       | `Optional[str]`            | Optional key so a retry of the same log is not stored twice. (default: `None`)                                                            |
| `metadata`                  | No       | `Optional[dict[str, Any]]` | Arbitrary key/value context stored separately from the typed payload. Surfaced in the Olira Console event detail panel. (default: `None`) |
| `write_back`                | No       | `bool`                     | Request write-back of this log into the org's connected system — see [`log`](#log). (default: `False`)                                       |
| `write_back_integration_id` | No       | `Optional[str]`            | Target integration instance for `write_back` when several are write-configured. (default: `None`)                                         |

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

## Integrations & Instances

Olira connects to a growing pool of integration providers — Epic, Healthie,
Vivlio, and more (`GET /v1/integrations/catalog` lists what's available). Every provider
follows the same connect → subscribe → sync → write-back pattern; the examples below use
Epic. An organization may connect **multiple integrations of the same type** — e.g. Epic
for Hospital A _and_ Epic for Hospital B — each a separate **instance** with its own id,
credentials, data point subscriptions, and patient identifier namespace.

**Data point availability depends on your connected app.** For Epic, the data points you
can subscribe to are determined by the Epic app registered for your health system (its
approved scopes/tier) — `GET /v1/integrations/{id}/data-points/catalog` already reflects
what your integration is entitled to. Other providers gate availability the same way
through their own credentials.

Integration management is available today as raw REST routes under `/v1/integrations`
(`sdk:integrations` scope); typed Python wrappers are planned. The essentials:

```bash
# Connect an instance — repeat with another hospital's URLs for a second instance
curl -X POST https://api.olira.ai/app-api/v1/integrations \
  -H "Authorization: Bearer $OLIRA_API_KEY" -H "Content-Type: application/json" \
  -d '{"integration_type": "epic", "display_name": "Epic — Hospital A",
       "auth_mode": "m2m",
       "credentials": {"type": "m2m_jwt", "client_id": "...",
         "token_endpoint": "https://<org>.epic.com/.../oauth2/token",
         "api_base_url": "https://<org>.epic.com/.../api/FHIR/R4"}}'
```

Key rules for SDK users:

- **Store the integration `id`** the connect call returns — data points, syncs, external-id
  lookups, and `write_back_integration_id` all key on it. Connecting the _same_ provider
  instance twice returns `409`; different instances of one type coexist.
- **Patient identity is instance-scoped.** Each instance's roster sync creates its own
  patients; the same human at two hospitals is two Olira patients (never merged
  implicitly). Your SDK-created patients and identifiers are untouched by this — see
  [External Identifiers](#external-identifiers).
- **Chart lookup per instance:** `GET /v1/integrations/{id}/patients/{patient_id}` returns
  the patient's integration-side id _at that instance_ (404 if the patient isn't known there).
- **Write-back targets an instance:** the `write_back` flag on [`log`](#log) /
  [`log_batch`](#log_batch) resolves its target integration automatically when
  unambiguous; pass `write_back_integration_id` when your org has several
  write-configured instances.

## Outbound Actions

All outbound-actions functions require an API key with the **`sdk:actions`** scope.

**Outbound actions** is how Olira notifies your systems when something happens on the platform: a patient's data updated, a log arrived that changed nothing, a mapping error, an ingestion job finished, or an integration failed to sync. You register a **destination** (a signed HTTPS webhook, or an email) and subscribe it to the triggers you care about. A failed webhook delivery retries automatically and eventually stops if it keeps failing; every attempt is recorded in a durable **delivery ledger** you can inspect and manually resend from. Everything you can do with destinations and deliveries in the Olira Console is available here.

See the full runnable walkthrough in [`examples/13_outbound_actions.py`](examples/13_outbound_actions.py).

### Triggers

| Trigger                                | Fires when                                                                                                     |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `patient.state.changed`                 | Something changed about a patient, such as new symptoms, lab results, or medications.                          |
| `log.no_state_change`                   | Olira received a log for a patient, but it didn't change anything we know about them.                          |
| `org.mapping.failed`                    | One of your incoming logs could not be translated into Olira's data model.                                     |
| `ingestion.completed`                   | A historical ingestion job you started finished successfully.                                                  |
| `ingestion.failed`                      | A historical ingestion job you started did not finish successfully.                                            |
| `integration.sync.failed`               | A sync of one of your connected integrations did not finish successfully.                                      |

Pass `["*"]` (or `ActionTrigger.ALL`) as `subscribed_triggers` to subscribe to every currently available trigger in the table above. `ActionTrigger` mirrors this table as a `StrEnum`; passing it instead of a plain string gets you autocomplete. A plain string still works everywhere an `ActionTrigger` is accepted (nothing validates it client-side, so a typo'd string still reaches the server as a 422). Because `"*"` is evaluated by the platform rather than by this list, a `"*"` subscription could start receiving additional trigger types later without another call on your part.

**Delivery volume: one delivery per trigger, by default.** Subscribing a destination to `patient.state.changed` (or any other high-frequency trigger) does not batch anything on its own: if 50 patients change state within the same minute, that's 50 separate deliveries, meaning 50 separate webhook calls or 50 separate emails, not one summary. This is rarely what you want for an email destination, and it can look like flooding even on a webhook pointed at a chat tool. If you're subscribing to a high-frequency trigger, decide up front whether you want immediate, one-per-event delivery (the default; correct for a pipeline that reacts to each change) or batched, one-per-day delivery (opt in via `digest_schedule`; see [Digest scheduling](#digest-scheduling) below) before you go live, not after the volume surprises you.

`RECOMMENDED_DIGEST_TRIGGERS` (a set containing `ActionTrigger.PATIENT_STATE_CHANGED`) flags the trigger frequent enough that the Olira Console itself defaults it to digest batching when you subscribe to it there. It's a suggested starting point, not a hard rule; every other currently available trigger is fine to leave on immediate delivery.

### Creating a destination

```python
from olira import ActionTrigger, WebhookDestinationConfig, EmailDestinationConfig

destination = client.create_action_destination(
    config=WebhookDestinationConfig(url="https://hooks.example.com/olira"),
    subscribed_triggers=[ActionTrigger.PATIENT_STATE_CHANGED, ActionTrigger.INGESTION_FAILED],
)
print(destination.signing_secret)  # shown once, store it now
```

`config` selects the destination type: pass a `WebhookDestinationConfig` (`url`, optional `api_version`) or an `EmailDestinationConfig` (`to_email`, optional `subject`/`from_name`). The returned `signing_secret` is shown in plaintext **exactly once**; it can be rotated (see `rotate_action_destination_secret`) but never retrieved again.

Your webhook `url` must be public HTTPS. `http://`, `localhost`, and private/internal addresses are rejected, both when you set the URL and again every time Olira sends to it.

---

### `create_action_destination`

```python
destination = client.create_action_destination(
    config=WebhookDestinationConfig(url="https://hooks.example.com/olira"),
    subscribed_triggers=[ActionTrigger.PATIENT_STATE_CHANGED],
    description="Acme webhook",
    rate_limit_per_minute=600,
)
# module-level: olira.create_action_destination(config=..., subscribed_triggers=..., ...)
```

**Parameters**

| Name                    | Type                                                         | Required | Description                                                                                                                       |
| ----------------------- | ------------------------------------------------------------ | -------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `config`                | `WebhookDestinationConfig \| EmailDestinationConfig \| dict` | Yes      | Destination type and its config. A raw `dict` is accepted for destination types not yet modeled by this SDK version. |
| `subscribed_triggers`   | `list[ActionTrigger \| str] \| None`                         | No       | Triggers this destination receives. `["*"]` = every currently available trigger in the table above.                               |
| `description`           | `str \| None`                                                | No       | Free-text description.                                                                                                            |
| `static_headers`        | `dict[str, str] \| None`                                     | No       | Extra headers replayed on every request (e.g. an API key your endpoint expects). Write-only, never read back.                     |
| `rate_limit_per_minute` | `int \| None`                                                | No       | Per-destination cap, 1 to 6000. Default 600.                                                                                      |
| `digest_schedule`       | `DigestSchedule \| None`                             | No       | Opt in to daily batching for high-frequency triggers; see [Digest scheduling](#digest-scheduling).                                |

**Returns** `ActionDestination`, including `signing_secret` (plaintext, shown once).

---

### `list_action_destinations`

```python
result = client.list_action_destinations()
for d in result.data:
    print(d.id, d.destination_type, d.status)
```

**Returns** `ActionDestinationListResult`: `data: list[ActionDestination]`, `total: int`. Secrets are never included, only `signing_secret_last4`.

---

### `get_action_destination`

```python
destination = client.get_action_destination(destination_id="dest_123")
```

**Parameters**

| Name             | Type  | Required | Description           |
| ---------------- | ----- | -------- | --------------------- |
| `destination_id` | `str` | Yes      | The destination's id. |

**Returns** `ActionDestination`.

---

### `update_action_destination`

```python
destination = client.update_action_destination(
    destination_id="dest_123",
    subscribed_triggers=["patient.state.changed", "ingestion.failed"],
)
```

Only the fields you pass are changed. `url`/`to_email`/`subject` must match the destination's own type.

Turning digest batching off needs its own flag, since simply omitting `digest_schedule` means "leave it as-is," not "remove it":

```python
# Turn digest batching OFF:
client.update_action_destination(destination_id="dest_123", clear_digest_schedule=True)

# Change the schedule:
client.update_action_destination(destination_id="dest_123", digest_schedule=DigestSchedule(time_of_day="09:00"))

# Leave the existing schedule untouched: omit both digest_schedule and clear_digest_schedule.
```

Passing both `digest_schedule` and `clear_digest_schedule=True` raises `ValueError`.

**Parameters**

| Name                    | Type                                 | Required | Description                                                                         |
| ----------------------- | ------------------------------------ | -------- | ----------------------------------------------------------------------------------- |
| `destination_id`        | `str`                                | Yes      | The destination's id.                                                               |
| `url`                   | `str \| None`                        | No       | New URL (webhook destinations only).                                                |
| `to_email`              | `str \| None`                        | No       | New recipient (email destinations only).                                            |
| `subject`               | `str \| None`                        | No       | New subject (email destinations only).                                              |
| `description`           | `str \| None`                        | No       | New description.                                                                    |
| `subscribed_triggers`   | `list[ActionTrigger \| str] \| None` | No       | Replaces the full subscription list.                                                |
| `status`                | `str \| None`                        | No       | `"active"` or `"disabled"`. Re-enabling clears the failure streak.                  |
| `static_headers`        | `dict[str, str] \| None`             | No       | Replaces the stored static headers.                                                 |
| `digest_schedule`       | `DigestSchedule \| None`     | No       | New digest schedule.                                                                |
| `clear_digest_schedule` | `bool`                               | No       | Pass `True` to turn digest batching off. Mutually exclusive with `digest_schedule`. |

**Returns** `ActionDestination`.

---

### `delete_action_destination`

```python
result = client.delete_action_destination(destination_id="dest_123")
print(result.dead_lettered_deliveries)
```

Disables the destination. Deliveries currently `pending`/`mapping`/`retrying` are stopped and will not be retried.

**Parameters**

| Name             | Type  | Required | Description           |
| ---------------- | ----- | -------- | --------------------- |
| `destination_id` | `str` | Yes      | The destination's id. |

**Returns** `ActionDestinationDeleteResult`.

---

### `rotate_action_destination_secret`

```python
destination = client.rotate_action_destination_secret(destination_id="dest_123")
print(destination.signing_secret)  # new secret, shown once
```

Generates a new signing secret. The **old secret stays valid for 24h** (dual-signing: the `Olira-Signature` header carries both during the overlap) so an in-progress rotation on the receiving end never drops a delivery.

**Parameters**

| Name             | Type  | Required | Description           |
| ---------------- | ----- | -------- | --------------------- |
| `destination_id` | `str` | Yes      | The destination's id. |

**Returns** `ActionDestination`, including the new `signing_secret` (plaintext, shown once).

---

### `list_action_deliveries`

```python
result = client.list_action_deliveries(destination_id="dest_123", status="delivered", limit=50)
for d in result.data:
    print(d.id, d.trigger, d.status)

# Paginate with the returned cursor:
cursor = result.next_cursor
while cursor is not None:
    page = client.list_action_deliveries(destination_id="dest_123", cursor=cursor)
    cursor = page.next_cursor
```

Newest first. `next_cursor` is `None` once you've reached the last page.

**Parameters**

| Name             | Type                           | Required | Description                                             |
| ---------------- | ------------------------------ | -------- | ------------------------------------------------------- |
| `destination_id` | `str \| None`                  | No       | Filter to one destination.                              |
| `status`         | `str \| None`                  | No       | Filter by delivery status.                              |
| `trigger`        | `ActionTrigger \| str \| None` | No       | Filter by trigger.                                      |
| `cursor`         | `str \| None`                  | No       | Pass the previous call's `next_cursor` to page forward. |
| `limit`          | `int \| None`                  | No       | Page size, 1 to 200. Default 50.                        |

**Returns** `ActionDeliveryListResult`: `data: list[ActionDelivery]` (no `payload` field on list rows; fetch one delivery for that), `next_cursor: str | None`.

---

### `get_action_delivery`

```python
delivery = client.get_action_delivery(delivery_id="del_123")
for attempt in delivery.attempts:
    print(attempt.attempt, attempt.outcome, attempt.http_status)
print(delivery.payload)  # the exact bytes sent
```

**Parameters**

| Name          | Type  | Required | Description        |
| ------------- | ----- | -------- | ------------------ |
| `delivery_id` | `str` | Yes      | The delivery's id. |

**Returns** `ActionDelivery`, including `payload`, the exact JSON Olira sent (or will send).

---

### `redeliver_action_delivery`

```python
new_delivery = client.redeliver_action_delivery(delivery_id="del_123")
```

Resends the same body as the original delivery, not a newly generated one. Creates a new delivery record with `redelivery_of` set to the original id. Works for up to 30 days after the original delivery.

Raises `ServerError` (HTTP 409) if the destination is currently disabled; re-enable it first.

**Parameters**

| Name          | Type  | Required | Description             |
| ------------- | ----- | -------- | ----------------------- |
| `delivery_id` | `str` | Yes      | The delivery to resend. |

**Returns** `ActionDelivery` (the new delivery record).

---

### Delivery payload

The body your webhook endpoint receives (or the JSON in `ActionDelivery.payload`) is a fixed envelope:

```json
{
  "id": "del_123",
  "type": "patient.state.changed",
  "created": "2026-08-12T09:14:05Z",
  "api_version": "2026-08-01",
  "data": { "...": "..." }
}
```

`type` carries the trigger you subscribed with, e.g. `"patient.state.changed"`; it's called `trigger` on `ActionDelivery` (the ledger record you read back through this SDK) and `type` in the payload itself (the envelope your endpoint parses). `data` is trigger-specific and holds ids and counts, not clinical field values:

| Trigger | `data` fields |
| --- | --- |
| `patient.state.changed` | `event_log_id`, `log_type`, `changed_paths`, `change_count`, `coalesced_count` (present when several updates for the same patient were folded into one delivery) |
| `log.no_state_change` | `event_log_id`, `log_type` |
| `org.mapping.failed` | `source_subtype`, `error_code` |
| `ingestion.completed` / `ingestion.failed` | `job_id`, `status`, `patient_count`, `record_count`, `failure_summary` (present only on partial failures) |
| `integration.sync.failed` | `integration_id`, `data_point_id`, `data_point_name`, `error`, `hint` (when known), `total_records`, `accepted`, `failed`, `unresolved` |

---

### Verifying the signature

Every delivery carries an `Olira-Signature` header: `t=<unix_ts>,v1=<hex_hmac>`. Recompute it with your destination's signing secret and compare; this proves the request came from Olira and wasn't altered in transit:

```python
import hashlib
import hmac
import time


def verify_signature(secret: str, header: str, raw_body: bytes, *, max_skew_seconds: int = 300) -> bool:
    fields = dict(part.split("=", 1) for part in header.split(",") if part.startswith("t="))
    try:
        timestamp = int(fields["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - timestamp) > max_skew_seconds:
        return False
    signatures = [part.split("=", 1)[1] for part in header.split(",") if part.startswith("v1=")]
    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)
```

During secret rotation the header carries **two** `v1=` entries; check if _any_ matches, don't assume there's exactly one. The timestamp is fresh on every attempt (including retries); reject a missing/malformed timestamp, one too far in the past (replay), or one unreasonably far in the future (clock skew or forgery) before checking the signature at all.

### Digest scheduling

A destination subscribed to a high-frequency trigger like `patient.state.changed` gets one delivery per event by default (see [Delivery volume](#triggers) above). `digest_schedule` opts a destination into batching those triggers into one delivery per day instead of one per event, correcting for exactly the flood scenario above:

```python
from olira import DigestSchedule

client.update_action_destination(
    destination_id="dest_123",
    digest_schedule=DigestSchedule(
        time_of_day="09:00",  # "HH:MM", on a :00 or :30 boundary; defaults to "09:00"
        timezone="America/New_York",  # IANA name; defaults to "UTC" if you don't set it
        triggers=["patient.state.changed"],  # must be a subset of subscribed_triggers
    ),
)
```

`time_of_day` defaults to `"09:00"` if you omit it. `timezone` defaults to `"UTC"`; set it explicitly to your organization's own timezone so the digest actually lands at a sensible local hour.

Only the listed `triggers` batch; anything else the destination is subscribed to still delivers immediately.

**Digested deliveries are not fast.** A digested trigger doesn't deliver right after it fires: it sits at `status: buffered` until your destination's `time_of_day` next arrives in its `timezone`, at which point every buffered delivery for that destination folds into a single delivery for the day. Depending on when the trigger fired relative to `time_of_day`, that can be close to a full day later, not a few minutes. If you're testing digest batching, don't poll `list_action_deliveries()` expecting a quick result the way you would for an immediate trigger.

### Outbound actions response models

### `ActionDestination`

| Field                       | Type                         | Description                                                                                                                   |
| --------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `id`                        | `str`                        | Olira-assigned destination id.                                                                                                |
| `project_id`                | `str \| None`                | Project this destination watches. `None` = the org's default project.                                                         |
| `destination_type`          | `str`                        | `"webhook"` or `"email"`.                                                                               |
| `status`                    | `ActionDestinationStatus`    | `"active"`, `"disabled"`, or `"auto_disabled"`.                                                                               |
| `description`               | `str \| None`                | Free-text description.                                                                                                        |
| `subscribed_triggers`       | `list[ActionTrigger \| str]` | Triggers this destination receives.                                                                                           |
| `config`                    | `dict`                       | Type-specific config, as returned by the server (URL, api_version, etc).                                                      |
| `signing_secret_last4`      | `str \| None`                | Last 4 characters of the current signing secret.                                                                              |
| `rate_limit_per_minute`     | `int \| None`                | Per-destination delivery rate cap.                                                                                            |
| `digest_schedule`           | `DigestSchedule \| None`     | Digest batching config, if enabled.                                                                                           |
| `consecutive_failures`      | `int`                        | Running failure streak. Resets to 0 on any successful delivery.                                                               |
| `failure_streak_started_at` | `str \| None`                | When the current failure streak began.                                                                                        |
| `auto_disabled_at`          | `str \| None`                | When the destination was auto-disabled (20+ consecutive failures over 72h+), if applicable.                                   |
| `rotated_at`                | `str \| None`                | When the signing secret was last rotated.                                                                                     |
| `signing_secret`            | `str \| None`                | Plaintext signing secret, present **only** on `create_action_destination()` / `rotate_action_destination_secret()` responses. |

`ActionDestinationListResult`: `data: list[ActionDestination]`, `total: int`.

`ActionDestinationDeleteResult`: `message: str`, `dead_lettered_deliveries: int`.

### `WebhookDestinationConfig`

| Field         | Type  | Description                            |
| ------------- | ----- | -------------------------------------- |
| `url`         | `str` | Must be HTTPS and publicly resolvable. |
| `api_version` | `str` | Defaults to the current API version.   |

### `EmailDestinationConfig`

| Field       | Type          | Description                   |
| ----------- | ------------- | ----------------------------- |
| `to_email`  | `str`         | Recipient address.            |
| `subject`   | `str \| None` | Optional subject override.    |
| `from_name` | `str \| None` | Optional sender display name. |

### `DigestSchedule`

| Field            | Type                         | Description                                                   |
| ---------------- | ---------------------------- | ------------------------------------------------------------- |
| `time_of_day`    | `str`                        | `"HH:MM"`, must land on a `:00` or `:30` boundary. Defaults to `"09:00"`. |
| `timezone`       | `str`                        | IANA timezone name. Defaults to `"UTC"`.                      |
| `triggers`       | `list[ActionTrigger \| str]` | Which subscribed triggers batch. |
| `last_sent_date` | `str \| None`                | Server-managed, ignored on write.                             |

### `ActionDelivery`

| Field                | Type                    | Description                                                                                        |
| -------------------- | ----------------------- | -------------------------------------------------------------------------------------------------- |
| `id`                 | `str`                   | Olira-assigned delivery id.                                                                        |
| `project_id`         | `str \| None`           | Project the source event belongs to.                                                               |
| `destination_id`     | `str`                   | The destination this delivery targets.                                                             |
| `destination_type`   | `str`                   | `"webhook"` or `"email"`.                                                                     |
| `trigger`            | `str`                   | The trigger that produced this delivery.                                                           |
| `event_id`           | `str`                   | Id of the occurrence that produced this delivery.                                                  |
| `status`             | `ActionDeliveryStatus`  | `pending`/`mapping`/`sending` (in flight), `delivered`, `skipped` (nothing to send), `retrying`, `dead_letter`, or `buffered` (parked for this destination's daily digest; see [Digest scheduling](#digest-scheduling) — it can sit here for up to a day, not just a few minutes). |
| `attempts`           | `list[DeliveryAttempt]` | Every attempt made so far, in order.                                                               |
| `next_attempt_at`    | `str \| None`           | When the next retry is scheduled, if `status == "retrying"`.                                       |
| `first_attempted_at` | `str \| None`           | Timestamp of the first attempt.                                                                    |
| `delivered_at`       | `str \| None`           | Timestamp of successful delivery.                                                                  |
| `dead_lettered_at`   | `str \| None`           | Timestamp when delivery stopped being retried, if applicable.                                                        |
| `last_error`         | `str \| None`           | The most recent error, if any.                                                                     |
| `redelivery_of`      | `str \| None`           | The original delivery id, if this record was created by `redeliver_action_delivery()`.             |
| `requested_by`       | `str \| None`           | Who initiated the delivery: `"redeliver:<actor>"` when a user manually resent it via `redeliver_action_delivery()`, some other value for an automatic delivery. |
| `batched_into`       | `str \| None`           | The daily digest this was included in, if any.                                          |
| `payload`            | `dict \| None`          | The exact JSON Olira sent, present **only** on `get_action_delivery()` responses.                 |

`ActionDeliveryListResult`: `data: list[ActionDelivery]`, `next_cursor: str | None`.

### `DeliveryAttempt`

| Field              | Type          | Description                                                |
| ------------------ | ------------- | ---------------------------------------------------------- |
| `attempt`          | `int`         | 1-based attempt number.                                    |
| `at`               | `str`         | Timestamp of this attempt.                                 |
| `outcome`          | `str`         | `"delivered"`, `"retryable_error"`, or `"terminal_error"`. |
| `http_status`      | `int \| None` | HTTP status code received, if any.                         |
| `error_code`       | `str \| None` | Error classification, if the attempt failed.               |
| `response_snippet` | `str \| None` | First 512 characters of the response body.                 |
| `duration_ms`      | `int \| None` | Attempt duration in milliseconds.                          |

---

## Patient Token

Patient tokens are short-lived JWTs scoped to a single patient. They are the bridge between your server-side API key and patient-facing or agent-facing calls to the [Olira MCP Patient State server](https://docs.olira.ai/mcp-server).

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
print(token.scopes)  # e.g. ["sdk:state-read", "sdk:event-log"]
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

The state-read methods give Python backends direct access to the same compiled patient state that the [MCP Patient State server](https://docs.olira.ai/mcp-server) exposes to AI agents — without going through JSON-RPC. They are a REST-backed mirror of the MCP tools, returning raw structured data rather than agent-formatted text.

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
| `logs` / `population_logs` | _(no MCP equivalent — SDK only)_      |
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
    # timestamp: when the event happened. ingested_at: when the platform received it.
    print(entry.type, entry.timestamp, entry.ingested_at, entry.payload)
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
      "ingested_at": "2026-03-18T10:00:00+00:00",
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
      "ingested_at": "2026-03-18T10:01:00+00:00",
      "payload": { "moods": [{ "mood": "anxious", "intensity": 3 }] },
      "trace": { "object_type": "conversation", "object_id": "conv-abc-123" }
    }
  ]
}
```

---

### Log query builder

`get_logs()` is a simple time-cursor fetch. Use `logs()` / `population_logs()` when you need richer filtering, field projection, or server-side aggregation. Both return a `LogQuery` (or `AsyncLogQuery`) builder that compiles a DSL spec and POSTs it to the server — no client-side query evaluation.

Requires `sdk:state-read` scope. Backend must be app-api ≥ 2.15.0.

#### `logs`

```python
client.logs(patient_id: str) -> LogQuery
```

Returns a builder scoped to one patient. Chain methods then call a terminal.

**Builder methods (all return `self` for chaining):**

| Category        | Method                                                 | Description                                                 |
| --------------- | ------------------------------------------------------ | ----------------------------------------------------------- |
| **Filters**     | `.eq(field, value)`                                    | Exact match                                                 |
|                 | `.neq(field, value)`                                   | Not equal                                                   |
|                 | `.gt / .gte / .lt / .lte`                              | Numeric / datetime comparisons                              |
|                 | `.in_(field, values)`                                  | Field value in list                                         |
|                 | `.nin(field, values)`                                  | Field value not in list                                     |
|                 | `.like(field, pattern)`                                | Case-sensitive SQL-style pattern (`%`)                      |
|                 | `.ilike(field, pattern)`                               | Case-insensitive pattern                                    |
|                 | `.is_(field, value)`                                   | Null / boolean match                                        |
|                 | `.exists(field, present=True)`                         | Field presence check                                        |
|                 | `.contains(field, value)`                              | Array / string contains                                     |
|                 | `.or_(*conditions)`                                    | OR group — pass `F(field).op(value)` expressions            |
|                 | `.and_(*conditions)`                                   | AND group                                                   |
| **Projection**  | `.select(*paths, **aliases)`                           | Include only named paths; `alias=path` kwargs rename fields |
|                 | `.select_array(path, *, where, element, first, alias)` | Array sub-field expansion                                   |
| **Ordering**    | `.order(field, desc=False)`                            | Sort                                                        |
| **Pagination**  | `.limit(n)`                                            | Max rows                                                    |
|                 | `.offset(n)`                                           | Skip rows                                                   |
|                 | `.range(start, end)`                                   | Inclusive slice (sets offset + limit)                       |
| **Aggregation** | `.group_by(*fields)`                                   | Group by field(s)                                           |
|                 | `.count_agg(alias)`                                    | Count per group                                             |
|                 | `.sum / .avg / .min / .max(field, alias)`              | Numeric aggregations                                        |
|                 | `.agg(op, field, alias=)`                              | Generic aggregation                                         |

**Allowed field roots:** `type`, `timestamp`, `ingested_at`, `trace`, `payload`. Any other root (e.g. `id`) returns HTTP 422 → `ValidationError`. See [`LogEntry`](#logentry) below for the `timestamp` vs. `ingested_at` distinction — both are valid to filter/order/select on.

**Terminals:**

| Terminal          | Returns          | Behaviour                                                                             |
| ----------------- | ---------------- | ------------------------------------------------------------------------------------- |
| `.execute()`      | `LogQueryResult` | All matching rows                                                                     |
| `.count()`        | `int`            | Count only; sets `count:true` in the body, no rows returned                           |
| `.single()`       | `dict`           | Exactly one row; `ValidationError` if 0 or > 1                                        |
| `.maybe_single()` | `dict \| None`   | Zero or one row; `ValidationError` if > 1                                             |
| `.as_logs()`      | `list[LogEntry]` | Execute and parse rows into typed `LogEntry`; only valid when no `.select()` was used |

**Examples:**

```python
import olira
from olira import F

olira.init(api_key="YOUR_API_KEY")

# Filter + order + limit
rows = (
    olira.logs("patient-uuid")
    .eq("type", "symptom_report")
    .gt("payload.score", 4)
    .order("timestamp", desc=True)
    .limit(25)
    .execute()
)
for row in rows:
    print(row["timestamp"], row["payload"])

# ilike + IN
rows = (
    olira.logs("patient-uuid")
    .ilike("payload.metric_type", "%pain%")
    .in_("type", ["symptom_report", "health_metric_reported"])
    .limit(10)
    .execute()
)

# OR boolean group via F()
rows = olira.logs("patient-uuid").or_(F("payload.score").gt(7), F("type").eq("mood_reported")).limit(10).execute()

# Projection with alias
rows = (
    olira.logs("patient-uuid")
    .eq("type", "health_metric_reported")
    .select("timestamp", score="payload.score")
    .limit(10)
    .execute()
)

# Count only
n = olira.logs("patient-uuid").eq("type", "symptom_report").count()

# Aggregation
agg = olira.logs("patient-uuid").group_by("type").count_agg("n").avg("payload.score", "avg_score").execute()

# maybe_single — returns None if empty, raises if > 1 row
row = (
    olira.logs("patient-uuid").eq("type", "demographics_updated").order("timestamp", desc=True).limit(1).maybe_single()
)

# Poll for everything the platform has ingested since your last check — use ingested_at,
# not timestamp: a backfill or delayed integration sync can insert old-timestamp rows at
# any time, so timestamp alone can silently skip events a timestamp-based cursor already
# passed. ingested_at only ever moves forward.
new_rows = olira.logs("patient-uuid").gt("ingested_at", last_poll_iso).order("ingested_at").execute()
```

#### `population_logs`

```python
client.population_logs(patient_ids: list[str] | None = None) -> LogQuery
```

Returns a builder scoped to the whole organisation (`patient_ids=None`) or an explicit cohort. Posts to `POST /v1/state/logs/query`. All builder and terminal methods are identical to `logs()`.

| Parameter     | Type                | Default | Description                                                            |
| ------------- | ------------------- | ------- | ---------------------------------------------------------------------- |
| `patient_ids` | `list[str] \| None` | `None`  | Cohort. `None` = whole org. Pass `[]` only if you intend an empty set. |

**Examples:**

```python
# Whole org — recent health_metric_reported events
rows = olira.population_logs().eq("type", "health_metric_reported").order("timestamp", desc=True).limit(50).execute()

# Explicit cohort
rows = olira.population_logs(patient_ids=["pid-1", "pid-2"]).gt("payload.score", 6).limit(100).execute()

# Org-wide aggregation
agg = olira.population_logs().group_by("type").count_agg("n").execute()
```

#### `F` — field expression helper

`F(field)` builds sub-condition dicts for use inside `.or_()` / `.and_()`. Every operator method on `F` mirrors the corresponding `LogQuery` filter method.

```python
from olira import F

# Inside an OR group:
.or_(F("payload.score").gt(7), F("type").eq("mood_reported"))

# Nested AND inside OR:
.or_(
    {"and": [F("type").eq("symptom_report"), F("payload.score").gt(6)]},
    F("type").eq("lab_results_received"),
)
```

`F` methods: `.eq`, `.neq`, `.gt`, `.gte`, `.lt`, `.lte`, `.in_`, `.nin`, `.like`, `.ilike`, `.is_`, `.exists`, `.contains` — each returns a condition dict.

#### `AsyncLogQuery`

`AsyncOliraClient.logs()` / `.population_logs()` return `AsyncLogQuery` with the same interface and `async def` terminals:

```python
async with AsyncOliraClient(api_key="YOUR_API_KEY") as client:
    rows = await client.logs("patient-uuid").eq("type", "symptom_report").limit(10).execute()
    n = await client.logs("patient-uuid").count()
    row = await client.logs("patient-uuid").eq("type", "demographics_updated").maybe_single()
```

---

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

| Field         | Type                 | Description                                                   |
| ------------- | -------------------- | ------------------------------------------------------------- |
| `id`          | `str`                | MongoDB document ID                                           |
| `type`        | `str \| None`        | Event type string                                             |
| `timestamp`   | `str \| None`        | ISO 8601 — when the event _happened_ (see below)              |
| `ingested_at` | `str \| None`        | ISO 8601 — when the platform _received_ the event (see below) |
| `payload`     | `dict[str, Any]`     | Event payload                                                 |
| `trace`       | `OliraTrace \| None` | Provenance trace                                              |

**`timestamp` vs. `ingested_at`:** `timestamp` is the event's own clock — when it actually
occurred (e.g. when a patient reported a symptom, or the source system's recorded observation time).
It's caller-supplied on write (see `log()`'s `timestamp` param, used to backdate historical
events) and is what logs are sorted by for a patient's timeline. `ingested_at` is server-set
and non-overridable — the moment app-api actually wrote the row — and is only ever populated
by the platform, never by a caller. The two commonly differ: a backfilled historical event
might have a `timestamp` from months ago but an `ingested_at` from today's import job; a
delayed integration sync might report a `timestamp` from the integration's roster pull with
`ingested_at` lagging by minutes or hours. Use `timestamp` to place events on the patient's
clinical timeline; use `ingested_at` to page/audit by when data actually landed on the
platform (e.g. "give me everything ingested since my last poll," which `timestamp` alone
can't answer reliably since backfills and delayed integration syncs can insert old-`timestamp`
rows at any time).

### `LogsResult`

| Field        | Type             | Description       |
| ------------ | ---------------- | ----------------- |
| `patient_id` | `str`            | Patient ID        |
| `count`      | `int`            | Number of entries |
| `logs`       | `list[LogEntry]` | Event log entries |

### `LogQueryResult`

Result of `LogQuery.execute()`. Iterable, indexable, and supports `len()`.

| Field             | Type          | Description                                                        |
| ----------------- | ------------- | ------------------------------------------------------------------ |
| `count`           | `int`         | Total rows matched (or just the count when `count:true`).          |
| `rows`            | `list[dict]`  | Projected / raw log dicts. Empty when `.count()` terminal is used. |
| `patient_id`      | `str \| None` | Echo of the queried patient id.                                    |
| `organization_id` | `str \| None` | Set on `population_logs()` queries.                                |

`.as_logs() -> list[LogEntry]` — validates `rows` into typed `LogEntry` objects. Only valid when no `.select()` was used (projection makes the dict shape arbitrary).

### `LogQuery` / `AsyncLogQuery`

Builder classes returned by `client.logs(patient_id)` and `client.population_logs(patient_ids)`. Not constructed directly. See the [Log query builder](#log-query-builder) section above for all methods.

### `F`

Field expression helper for `.or_()` / `.and_()` conditions. Constructed as `F("field.path")`. Methods — `.eq`, `.neq`, `.gt`, `.gte`, `.lt`, `.lte`, `.in_`, `.nin`, `.like`, `.ilike`, `.is_`, `.exists`, `.contains` — each returns a condition dict accepted by the builder.

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

## Passive Signal Ingestion

Upload multi-Hz **accelerometer**, **gyroscope**, or **GPS** batches as Parquet.
Canonical guide (pipeline, REST doors, handoff, dedup):
[Passive signal ingestion](https://docs.olira.ai/send-data/passive-signals).

**Requires** an API key with the `sdk:event-log` scope. For `records=` serialization,
install `pip install olira[signals]` (or pass pre-serialized `parquet=` bytes).

### Handoff contract

1. Doors land bytes in the **S3 lake** (provenance / replay only — never a query surface).
2. The absorb worker normalizes and writes **Timescale** (deduped, UTC, canonical units).
3. **Feature compute reads Timescale only**, never the lake. Derived features emit as
   `activity_data` event logs.

### Dedup policy (accepted for ≤500 Hz sensors)

- Timestamps are truncated to **milliseconds** at normalize time.
- Unique key: `(patient_id, source_device, ts)`.
- Re-uploads of the same instant **first-wins** (`ON CONFLICT DO NOTHING`).
- Landing may also no-op on exact content-hash match (`deduplicated: true` on sync accept).
- A sample-sequence tiebreaker is deferred until a sensor above ~500 Hz needs it.

### Quickstart

```python
from datetime import datetime, timezone
from olira import OliraClient

client = OliraClient(api_key="YOUR_API_KEY")

handle = client.send_signals(
    patient_id="PATIENT_ID",
    sensor_type="accelerometer",
    source_device="phone-imu-1",
    sample_rate_hz=60.0,
    records=[
        {"ts": datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc), "x": 0.1, "y": 0.0, "z": 9.8},
    ],
)
job = handle.wait()
print(job.status, job.records_written, job.records_deduplicated)
```

The SDK routes small bodies to `POST /v1/signals:batch` and large bodies to
`:upload-url` + S3 PUT + `:manifest`. Do **not** send `Authorization` on the
presigned PUT.

Poll with `client.get_signal_job(job_id=...)`. Dead-letters and metrics are REST-only
(`GET /v1/signals/dead-letters`, `GET /v1/signals/metrics`) — see the docs site.

---

## Batch Export

Export patient data as a ZIP of Parquet files for offline analytics. Requires
`sdk:state-read`. Provide exactly one of `patient_ids`, `cohort_id`, or
`scope="project"`.

### Create and download

```python
import time
from datetime import datetime, timezone
from olira import Olira, ExportInclude

client = Olira(api_key="olk_...")

job = client.create_export(
    start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end=datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
    include=ExportInclude(
        logs=True,
        state_modules=True,
        view_blocks=True,
        events=True,
        extracted=False,
    ),
    patient_ids=["patient_abc123"],
)

while job.status not in ("completed", "failed", "cancelled"):
    time.sleep(5)
    job = client.get_export(export_id=job.export_id)

if job.status != "completed":
    raise RuntimeError(job.error_message or job.status)

download = client.download_export(export_id=job.export_id)
# download.download_url is a short-lived presigned HTTPS URL to the ZIP
```

### ZIP layout

| Member           | Contents                                      |
| ---------------- | --------------------------------------------- |
| `logs/`          | Event-log rows as Parquet                     |
| `state_modules/` | Patient state modules as Parquet              |
| `view_blocks/`   | Summary view blocks as Parquet                |
| `events/`        | Derived events as Parquet                     |
| `extracted/`     | Extracted document text as Parquet (optional) |

Omit a category with `ExportInclude(..., logs=False)` (etc.). List jobs with
`client.list_exports(limit=20)`.

C# uses the same endpoints via `OliraModule.CreateExport` / `GetExport` /
`ListExports` / `DownloadExport`.

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
    idempotency_key="initial-onboarding-2026",  # optional but recommended
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
        IngestRecord.patient(
            CreatePatientRequest(
                first_name="Jane",
                last_name="Smith",
                date_of_birth="1980-03-22T00:00:00Z",
                external_identifiers=[ExternalIdentifier(system="epic", value="MRN-12345")],
            )
        ),
        IngestRecord.log(
            IngestLogSpec(
                event_type="symptom_report",
                # patient_id can be an external_identifier value (any system) or an Olira patient UUID
                patient_id="MRN-12345",
                # timestamp backdates the event — this is how historical events are placed correctly
                # in the patient timeline. Use ISO 8601 with timezone offset or trailing 'Z'.
                timestamp="2025-01-15T09:00:00Z",
                payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 3}]},
                idempotency_key="report-001",  # strongly recommended — prevents duplicates on retry
            )
        ),
    ],
    idempotency_key="lab-backfill-batch-1",
    require_confirmation=False,  # run straight through without review pause
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

Cancel a job. Cleanup is server-defined:

- **Pre-Load** (review pause / before ontology commit) — leftover STALE logs for the job are deleted, and **job-created** patients with no other EventLog history are hard-deleted. S3 staging zones are left in place.
- **Post-Load** — soft-stop only. Partial committed ontology (COMPLETED EventLogs / modules / views already written) is **retained**.

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

**Data state:** On `FAILED`, patient documents created are retained unless you cancel (pre-Load cancel removes eligible job-created patients).

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

| Field             | Type                 | Required | Description                                        |
| ----------------- | -------------------- | -------- | -------------------------------------------------- |
| `event_type`      | `str`                | Yes      | Platform event type (e.g. `"symptom_report"`)      |
| `patient_id`      | `str`                | Yes      | Olira patient UUID or `external_identifier` value  |
| `timestamp`       | `str`                | Yes      | ISO 8601 datetime                                  |
| `payload`         | `dict`               | No       | Event-specific payload                             |
| `idempotency_key` | `str`                | No       | Prevents duplicate insertion on retry              |
| `trace`           | `OliraTrace \| None` | No       | Optional provenance; both fields required when set |

#### `IngestionJobListResult`

| Field   | Type                 | Description              |
| ------- | -------------------- | ------------------------ |
| `total` | `int`                | Total jobs for the org   |
| `jobs`  | `list[IngestionJob]` | Jobs in the current page |
