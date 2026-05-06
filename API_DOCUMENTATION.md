> **Maintained by:** Olira Engineering  
> **Published at:** `olira.ai/api-docs` → Python SDK tab  
> **Status:** **BETA** — SDK APIs and this reference may change between releases.

# Olira Python SDK — API Reference

The Olira Python SDK provides a typed client for logging health events,
managing patients, and minting patient-scoped tokens for use with the
[Olira MCP Patient State server](https://olira.ai/api-docs).

**Package:** `olira` — **Version:** `0.1.0a8`


## Related docs

| Doc | What it covers | Why you need it |
| --- | -------------- | --------------- |
| **Authentication** (`olira.ai/api-docs` → Authentication tab) | API keys, patient tokens, **scopes**, auth errors | Choose scopes when creating keys; mint patient tokens for device-facing calls |
| **MCP Patient State** (`olira.ai/api-docs` → MCP tab) | Tools for querying patient health state from AI agents | The events you log with this SDK populate the patient state the MCP server exposes; `get_patient_token()` mints the tokens used to authenticate patient-facing MCP requests |
| **CLI** (`olira.ai/api-docs` → CLI tab) | `olira login`, `olira keys create`, `olira configure cursor` | Create and rotate the API keys passed to `olira.init()`; configure Cursor to use the MCP server |


## Getting Started

### Installation

```bash
pip install olira
```

Or with `uv`:

```bash
uv add olira
```

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

Use `OliraClient` directly when you need multiple keys or prefer
dependency injection:

```python
from olira import OliraClient

client = OliraClient(api_key="YOUR_OLIRA_API_KEY")
```

### `init()` — module-level initialisation

#### `init`

```python
init(api_key: str | None = None, *, environment: OliraEnv = OliraEnv.PRODUCTION, service_name: str | None = None, base_url: str = 'https://api.prod.olira.ai', batch_size: int = 50, flush_interval: float = 1.5, max_queue_size: int = 10000, timeout: float = 5.0, max_retries: int = 3, on_error: str = 'drop', async_flush: bool = True) -> None
```

Initialize the SDK. API key can be passed or set via OLIRA_API_KEY env var.

| Parameter        | Required | Type       | Default                       |
| ---------------- | -------- | ---------- | ----------------------------- |
| `api_key`        | No       | `Optional[str]`                         | `None` |
| `environment`    | No       | `OliraEnv` | `OliraEnv.PRODUCTION`         |
| `service_name`   | No       | `Optional[str]`                         | `None` |
| `base_url`       | No       | `str`      | `'https://api.prod.olira.ai'` |
| `batch_size`     | No       | `int`      | `50`                          |
| `flush_interval` | No       | `float`    | `1.5`                         |
| `max_queue_size` | No       | `int`      | `10000`                       |
| `timeout`        | No       | `float`    | `5.0`                         |
| `max_retries`    | No       | `int`      | `3`                           |
| `on_error`       | No       | `str`      | `'drop'`                      |
| `async_flush`    | No       | `bool`     | `True`                        |


## Olira CLI

The CLI ships separately and provides local tooling for API key management
and Cursor configuration. Install it with:

```bash
pip install olira-cli
```

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

### Helper models

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

| Field         | Required | Type  | Description                                                     |
| ------------- | -------- | ----- | --------------------------------------------------------------- |
| `object_type` | Yes      | `str` | Category of the linked object, e.g. `'conversation'`, `'message'`, `'questionnaire'` |
| `object_id`   | Yes      | `str` | Your identifier for the linked object                           |

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

### `TimePeriod`

Time range in ISO 8601 datetimes. Wire-compatible with PeriodRange in common-models util.py.

| Field            | Required | Type  | Description |
| ---------------- | -------- | ----- | ----------- |
| `start_datetime` | Yes      | `str` | —           |
| `end_datetime`   | Yes      | `str` | —           |

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

Requires an API key with the api:manage-patients scope. Returns a :class:`Patient`
with an Olira-assigned `id` — use it in all subsequent calls for this patient.

**Anchor rule (validation):** You must provide **at least one** of: a non-empty `external_identifiers` list, `email`, non-empty `phone_number`, `first_name`, `last_name`, or `date_of_birth`. Omitting all of these raises a validation error. This allows **shell** patients (for example, an external EMR id only) until demographics are synced or entered later via `update_patient`.

| Parameter              | Required | Type                             | Default     |
| ---------------------- | -------- | -------------------------------- | ----------- |
| `first_name`           | No       | `str \| None`                    | `None`      |
| `last_name`            | No       | `str \| None`                    | `None`      |
| `email`                | No       | `str \| None`                    | `None`      |
| `phone_number`         | No       | `str \| None`                    | `None`      |
| `date_of_birth`        | No       | `str \| None`                    | `None`      |
| `sex`                  | No       | `str`                            | `'unknown'` |
| `timezone`             | No       | `str`                            | `'UTC'`     |
| `primary_disease_site` | No       | `str \| None`                    | `None`      |
| `disease_stage`        | No       | `str \| None`                    | `None`      |
| `external_identifiers` | No       | `list[ExternalIdentifier] \| None` | `None` (sent as `[]`) |
| `metadata`             | No       | `dict[str, Any] \| None`         | `None`      |

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

| Parameter         | Required | Type  | Default |
| ----------------- | -------- | ----- | ------- |
| `limit`           | No       | `int` | `100`   |
| `offset`          | No       | `int` | `0`     |
| `external_system` | No       | `Optional[str]`   | `None` |
| `external_value`  | No       | `Optional[str]`   | `None` |

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

| Parameter              | Required | Type                      | Default |
| ---------------------- | -------- | ------------------------- | ------- |
| `patient_id`           | Yes      | `str`                     | —       |
| `first_name`           | No       | `Optional[str]`   | `None` |
| `last_name`            | No       | `Optional[str]`   | `None` |
| `email`                | No       | `Optional[str]`   | `None` |
| `phone_number`         | No       | `Optional[str]`   | `None` |
| `sex`                  | No       | `Optional[str]`   | `None` |
| `timezone`             | No       | `Optional[str]`   | `None` |
| `primary_disease_site` | No       | `Optional[str]`   | `None` |
| `disease_stage`        | No       | `Optional[str]`   | `None` |
| `external_identifiers` | No       | `Optional[list[ExternalIdentifier]]`   | `None` |
| `metadata`             | No       | `Optional[dict[str, Any]]`   | `None` |

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
Returns a :class:`PatientBatchResult` with items (successes) and errors (failures).

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

Olira assigns a stable `id` at creation time — it is returned on the :class:`Patient` response. The same **anchor rule** as `create_patient` applies: at least one of `external_identifiers` (non-empty), `email`, `phone_number`, `first_name`, `last_name`, or `date_of_birth` must be set. Optional demographics support **shell** patients.

| Field                  | Required | Type                             | Description |
| ---------------------- | -------- | -------------------------------- | ----------- |
| `first_name`           | No       | `str \| None`                    | Given name; omit for shell patients. |
| `last_name`            | No       | `str \| None`                    | Family name; omit for shell patients. |
| `email`                | No       | `str \| None`                    | —           |
| `phone_number`         | No       | `str \| None`                    | —           |
| `date_of_birth`        | No       | `str \| None`                    | ISO 8601 when set, e.g. `1985-03-22T00:00:00Z`. |
| `sex`                  | No       | `str`                            | Default `'unknown'`. |
| `timezone`             | No       | `str`                            | Default `'UTC'`. |
| `primary_disease_site` | No       | `str \| None`                    | —           |
| `disease_stage`        | No       | `str \| None`                    | —           |
| `external_identifiers` | No       | `list[ExternalIdentifier]`       | Default `[]`. Non-empty list satisfies the anchor rule. |
| `metadata`             | No       | `dict[str, Any] \| None`         | —           |

### `UpdatePatientRequest`

Request body for updating a patient (all fields optional).

Only the fields you set are changed; omitted fields are left as-is.

| Field                  | Required | Type                      | Description |
| ---------------------- | -------- | ------------------------- | ----------- |
| `first_name`           | No       | `Optional[str]`       | — (default: `None`) |
| `last_name`            | No       | `Optional[str]`       | — (default: `None`) |
| `email`                | No       | `Optional[str]`       | — (default: `None`) |
| `phone_number`         | No       | `Optional[str]`       | — (default: `None`) |
| `sex`                  | No       | `Optional[str]`       | — (default: `None`) |
| `timezone`             | No       | `Optional[str]`       | — (default: `None`) |
| `primary_disease_site` | No       | `Optional[str]`       | — (default: `None`) |
| `disease_stage`        | No       | `Optional[str]`       | — (default: `None`) |
| `external_identifiers` | No       | `Optional[list[ExternalIdentifier]]`       | — (default: `None`) |
| `metadata`             | No       | `Optional[dict[str, Any]]`       | — (default: `None`) |

### `Patient`

A patient in your organisation.

`id` is the Olira-assigned identifier for this patient, returned at creation
time. Use it in all subsequent calls that reference this patient.

Demographics may be absent for shell patients created with only an external id or partial data; `first_name`, `last_name`, and `sex` are then `None`.

| Field                  | Required | Type                       | Description           |
| ---------------------- | -------- | -------------------------- | --------------------- |
| `id`                   | Yes      | `str`                      | Olira-assigned id.   |
| `first_name`           | No       | `str \| None`              | `None` if unknown.   |
| `last_name`            | No       | `str \| None`              | `None` if unknown.   |
| `sex`                  | No       | `str \| None`              | `None` if unknown.   |
| `timezone`             | Yes      | `str`                      | IANA timezone.       |
| `status`               | Yes      | `str`                      | Account status.      |
| `email`                | No       | `str \| None`              | —                     |
| `phone_number`         | No       | `str \| None`              | —                     |
| `date_of_birth`        | No       | `str \| None`              | ISO 8601 when set.   |
| `primary_disease_site` | No       | `str \| None`              | —                     |
| `disease_stage`        | No       | `str \| None`              | —                     |
| `created_at`           | No       | `str \| None`              | —                     |
| `external_identifiers` | No       | `list[ExternalIdentifier]` | May be empty.        |
| `metadata`             | No       | `dict[str, Any] \| None`   | —                     |

### `PatientListResult`

Result of a list_patients() call.

| Field      | Required | Type            | Description |
| ---------- | -------- | --------------- | ----------- |
| `patients` | Yes      | `list[Patient]` | —           |
| `total`    | Yes      | `int`           | —           |
| `has_more` | Yes      | `bool`          | —           |

### `PatientBatchItem`

One successfully created patient from a batch_create_patients() call.

| Field    | Required | Type  | Description |
| -------- | -------- | ----- | ----------- |
| `index`  | Yes      | `int` | —           |
| `id`     | Yes      | `str` | —           |
| `source` | No       | `Optional[str]`       | — (default: `None`) |

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

### Log a single event

#### `log`

```python
log(*, log_type: OliraLogType, patient_id: str, payload: dict[str, Any] | None = None, trace: OliraTrace | None = None, timestamp: str | None = None) -> None
```

Enqueue an event for background delivery. Module-level proxy to the singleton client.

| Parameter    | Required | Type             | Default |
| ------------ | -------- | ---------------- | ------- |
| `log_type` | Yes      | `OliraLogType` | —       |
| `patient_id` | Yes      | `str`            | —       |
| `payload`    | No       | `Optional[dict[str, Any]]`   | `None` |
| `trace`      | No       | `Optional[OliraTrace]`   | `None` |
| `timestamp`  | No       | `Optional[str]`   | `None` |

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

| Parameter | Required | Type              | Default |
| --------- | -------- | ----------------- | ------- |
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

### Log response models

### `LogSpec`

Lightweight event specification for log_batch(). Not persisted internally.

| Field             | Required | Type             | Description |
| ----------------- | -------- | ---------------- | ----------- |
| `log_type`      | Yes      | `OliraLogType` | —           |
| `patient_id`      | Yes      | `str`            | —           |
| `payload`         | No       | `Optional[dict[str, Any]]`       | — (default: `None`) |
| `trace`           | No       | `Optional[OliraTrace]`       | — (default: `None`) |
| `timestamp`       | No       | `Optional[str]`       | — (default: `None`) |
| `idempotency_key` | No       | `Optional[str]`       | — (default: `None`) |

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

### Mint a patient-scoped JWT

#### `get_patient_token`

```python
get_patient_token(*, patient_id: str) -> PatientToken
```

Mint a short-lived patient-scoped JWT. Module-level proxy to the singleton client.

Requires an API key with the sdk:patient-token scope.
The returned JWT can be used as a Bearer token with the Olira MCP Patient State server.

| Parameter    | Required | Type  | Default |
| ------------ | -------- | ----- | ------- |
| `patient_id` | Yes      | `str` | —       |

Requires `sdk:patient-token` scope. The token is locked to the patient
and can be used as a Bearer token with the Olira MCP Patient State server.

**Example:**

```python
token = olira.get_patient_token(patient_id="patient-uuid")
# Pass token.access_token to your frontend / AI agent
print(f"Token expires in {token.expires_in}s")
```


## Patient State — Read

The state-read methods give Python backends direct access to the same compiled patient state that the [MCP Patient State server](https://olira.ai/api-docs) exposes to AI agents — without going through JSON-RPC. They are a REST-backed mirror of the MCP tools, returning raw structured data rather than agent-formatted text.

All state-read functions require an API key with the `sdk:state-read` scope.

| SDK method | MCP tool equivalent |
| --- | --- |
| `get_stable_data` | `get_stable_data` |
| `list_event_state_modules` | `list_event_state_modules` |
| `get_event_state_module` | `get_event_state_module` |
| `list_views` | `list_views_and_blocks` (list mode) |
| `list_view_blocks` | `list_views_and_blocks` (blocks mode) |
| `get_view` | `get_view` |
| `get_view_block` | `get_view_block` |
| `get_view_recent_events` | `get_view_recent_events` |
| `get_logs` | `get_logs` |
| `get_events` | `get_events` |
| `read_memories` | `read_memories` (list-all mode) |

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

| Parameter    | Required | Type            | Default |
| ------------ | -------- | --------------- | ------- |
| `patient_id` | Yes      | `str`           | —       |
| `modules`    | No       | `list[str] \| None` | `None` (all) |

Valid module names (`StableModuleType`): `demographics`, `condition_diagnosis`, `medications`, `user_preferences`, `emergency_contact`, `care_team`, `insurance`, `social`, `pharmacy`, `procedures`, `allergies`, `immunizations`, `devices`, `family_history`. Which are populated depends on what data has been ingested for this patient. Omit `modules` to fetch all.

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
      "payload": {"value": {"first_name": "Jane", "last_name": "Smith", "date_of_birth": "1975-06-15", "sex": "female", "timezone": "America/New_York"}},
      "created_at": "2026-01-10T08:00:00+00:00",
      "updated_at": "2026-03-18T14:22:00+00:00"
    },
    "condition_diagnosis": {
      "module_type": "condition_diagnosis",
      "payload": {"value": {"primary_disease_site": "breast", "disease_stage": "Stage II"}},
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
  {"module_type": "symptoms", "updated_at": "2026-03-18T10:00:00+00:00", "created_at": "2026-01-10T08:00:00+00:00"},
  {"module_type": "adherence", "updated_at": "2026-03-17T09:30:00+00:00", "created_at": "2026-01-10T08:00:00+00:00"},
  {"module_type": "engagement", "updated_at": "2026-03-18T12:00:00+00:00", "created_at": "2026-01-10T08:00:00+00:00"}
]
```

#### `get_event_state_module`

```python
get_event_state_module(*, patient_id: str, module_type: str) -> EventStateModuleResult
```

Get a specific event state module by type. Mirrors `get_event_state_module` on the MCP.

Valid module types (`EventStateModuleType`): `symptoms`, `emotional_state`, `adherence`, `physical_activity`, `engagement`, `heart`, `sleep`, `lab_results`, `vitals`, `clinical_context`, `questionnaires`, `conversations`, `glucose`. Use `list_event_state_modules()` to discover which are present and populated for a specific patient.

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
      {"name": "pain", "score": 4, "ctcae_grade": 1, "updated_at": "2026-03-18T10:00:00+00:00"},
      {"name": "fatigue", "score": 6, "ctcae_grade": 2, "updated_at": "2026-03-18T10:00:00+00:00"}
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
  {"view_type": "symptom_snapshot", "view_id": "66f1a2b3c4d5e6f7a8b9c0d1", "has_blocks": true, "has_temp": true},
  {"view_type": "medication_snapshot", "view_id": "66f1a2b3c4d5e6f7a8b9c0d2", "has_blocks": true, "has_temp": true}
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
      {"id": "symptom_overview", "name": "Symptom Overview", "text": "Patient reported moderate pain (4/10) and significant fatigue (6/10) over the past 7 days."},
      {"id": "symptom_trends", "name": "Symptom Trends", "text": "Fatigue has been stable week-over-week. Pain has increased from 3/10 to 4/10."}
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

| Parameter     | Required | Type              | Default |
| ------------- | -------- | ----------------- | ------- |
| `patient_id`  | Yes      | `str`             | —       |
| `since`       | No       | `str \| None`     | `None`  |
| `limit`       | No       | `int`             | `50`    |
| `log_types` | No       | `list[str] \| None` | `None` |
| `trace_type`  | No       | `str \| None`     | `None`  |
| `trace_id`    | No       | `str \| None`     | `None`  |

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
      "payload": {"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 4}, {"name": "fatigue", "score": 6}]},
      "trace": {"object_type": "conversation", "object_id": "conv-abc-123"}
    },
    {
      "id": "66f1a2b3c4d5e6f7a8b9c0d4",
      "type": "moods_report",
      "timestamp": "2026-03-18T10:01:00+00:00",
      "payload": {"moods": [{"mood": "anxious", "intensity": 3}]},
      "trace": {"object_type": "conversation", "object_id": "conv-abc-123"}
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

| Field         | Type                    | Description                   |
| ------------- | ----------------------- | ----------------------------- |
| `module_type` | `str`                   | Module key                    |
| `payload`     | `dict \| None`          | Raw module data               |
| `created_at`  | `str \| None`           | ISO 8601 timestamp            |
| `updated_at`  | `str \| None`           | ISO 8601 timestamp            |

### `StableDataResult`

| Field       | Type                        | Description              |
| ----------- | --------------------------- | ------------------------ |
| `patient_id` | `str`                      | Patient ID               |
| `modules`   | `dict[str, StableModule]`   | Modules keyed by type    |

### `EventStateModuleSummary`

| Field         | Type          | Description        |
| ------------- | ------------- | ------------------ |
| `module_type` | `str`         | Module type key    |
| `updated_at`  | `str \| None` | ISO 8601 timestamp |
| `created_at`  | `str \| None` | ISO 8601 timestamp |

### `EventStateModuleResult`

| Field         | Type                        | Description        |
| ------------- | --------------------------- | ------------------ |
| `patient_id`  | `str`                       | Patient ID         |
| `module_type` | `str`                       | Module type        |
| `payload`     | `dict \| list \| None`      | Module data        |
| `created_at`  | `str \| None`               | ISO 8601 timestamp |
| `updated_at`  | `str \| None`               | ISO 8601 timestamp |

### `ViewMeta`

| Field        | Type   | Description                   |
| ------------ | ------ | ----------------------------- |
| `view_type`  | `str`  | View type key                 |
| `view_id`    | `str`  | MongoDB document ID           |
| `has_blocks` | `bool` | Unified block list available  |
| `has_temp`   | `bool` | TEMP (live) entries available |

### `ViewResult`

| Field        | Type              | Description                             |
| ------------ | ----------------- | --------------------------------------- |
| `patient_id` | `str`             | Patient ID                              |
| `view_type`  | `str`             | View type                               |
| `view_id`    | `str \| None`     | MongoDB document ID                     |
| `valid_from` | `str \| None`     | View coverage start (ISO 8601)          |
| `valid_to`   | `str \| None`     | View coverage end (ISO 8601)            |
| `content`    | `dict[str, Any]`  | `"blocks"` → unified block list; `"temp"` → live TEMP entries |

### `ViewBlockResult`

| Field         | Type                       | Description             |
| ------------- | -------------------------- | ----------------------- |
| `patient_id`  | `str`                      | Patient ID              |
| `view_type`   | `str`                      | View type               |
| `block_id`    | `str`                      | Block identifier        |
| `content`     | `str \| None`              | Generated block text (raw, without MCP's pretty-print header) |
| `confidences` | `dict[str, float] \| None` | Confidence scores       |
| `updated_at`  | `str \| None`              | ISO 8601 timestamp      |

### `ViewRecentEventsResult`

| Field        | Type        | Description                        |
| ------------ | ----------- | ---------------------------------- |
| `patient_id` | `str`       | Patient ID                         |
| `view_type`  | `str`       | View type                          |
| `entries`    | `list[str]` | TEMP entries (most recent `limit`) |
| `count`      | `int`       | Number of entries returned         |
| `total_count`| `int`       | Total TEMP entries in store        |

### `LogEntry`

| Field       | Type                 | Description         |
| ----------- | -------------------- | ------------------- |
| `id`        | `str`                | MongoDB document ID |
| `type`      | `str \| None`        | Event type string   |
| `timestamp` | `str \| None`        | ISO 8601 timestamp  |
| `payload`   | `dict[str, Any]`     | Event payload       |
| `trace`     | `OliraTrace \| None` | Provenance trace    |

### `LogsResult`

| Field        | Type              | Description       |
| ------------ | ----------------- | ----------------- |
| `patient_id` | `str`             | Patient ID        |
| `count`      | `int`             | Number of entries |
| `logs`       | `list[LogEntry]`  | Event log entries |

### `EventEntry`

| Field                 | Type           | Description                    |
| --------------------- | -------------- | ------------------------------ |
| `id`                  | `str`          | MongoDB document ID            |
| `trigger`             | `str \| None`  | `event_log` or `summary_block` |
| `log_type`            | `str \| None`  | Originating event type         |
| `status`              | `str \| None`  | `complete`, `pending`, `failed`|
| `triggered_at`        | `str \| None`  | ISO 8601 timestamp             |
| `completed_at`        | `str \| None`  | ISO 8601 timestamp             |
| `source_event_log_id` | `str \| None`  | Originating EventLog ID        |
| `log_payload`         | `dict \| None` | Payload from the source event  |
| `changes`             | `dict \| None` | State changes applied          |

### `EventsResult`

| Field        | Type                  | Description       |
| ------------ | --------------------- | ----------------- |
| `patient_id` | `str`                 | Patient ID        |
| `count`      | `int`                 | Number of entries |
| `events`     | `list[EventEntry]`    | Events |

### `MemoryEntry`

| Field        | Type               | Description          |
| ------------ | ------------------ | -------------------- |
| `memory_id`  | `str`              | Memory identifier    |
| `content`    | `str`              | Memory text          |
| `metadata`   | `dict \| None`     | Optional metadata    |
| `created_at` | `str \| None`      | ISO 8601 timestamp   |
| `updated_at` | `str \| None`      | ISO 8601 timestamp   |

### `MemoriesResult`

| Field        | Type                 | Description       |
| ------------ | -------------------- | ----------------- |
| `patient_id` | `str`                | Patient ID        |
| `count`      | `int`                | Number of results |
| `results`    | `list[MemoryEntry]`  | Memory records    |


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
