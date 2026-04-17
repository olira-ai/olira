> **Maintained by:** Olira Engineering  
> **Published at:** `olira.ai/api-docs` → Python SDK tab

# Olira Python SDK — API Reference

The Olira Python SDK provides a typed client for logging health events,
managing patients, and minting patient-scoped tokens for use with the
[Olira MCP Patient State server](https://olira.ai/api-docs).

**Package:** `olira` — **Version:** `0.1.0a7`

---

## Related docs

| Doc | What it covers | Why you need it |
| --- | -------------- | --------------- |
| **MCP Patient State** (`olira.ai/api-docs` → MCP tab) | Tools for querying patient health state from AI agents | The events you log with this SDK populate the patient state the MCP server exposes; `get_patient_token()` mints the tokens used to authenticate patient-facing MCP requests |
| **CLI** (`olira.ai/api-docs` → CLI tab) | `olira login`, `olira keys create`, `olira configure cursor` | Create and rotate the API keys passed to `olira.init()`; configure Cursor to use the MCP server |

---

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
| ---------------- | -------- | ---------- | ----------------------------- | ------ |
| `api_key`        | No       | `str       | None`                         | `None` |
| `environment`    | No       | `OliraEnv` | `OliraEnv.PRODUCTION`         |
| `service_name`   | No       | `str       | None`                         | `None` |
| `base_url`       | No       | `str`      | `'https://api.prod.olira.ai'` |
| `batch_size`     | No       | `int`      | `50`                          |
| `flush_interval` | No       | `float`    | `1.5`                         |
| `max_queue_size` | No       | `int`      | `10000`                       |
| `timeout`        | No       | `float`    | `5.0`                         |
| `max_retries`    | No       | `int`      | `3`                           |
| `on_error`       | No       | `str`      | `'drop'`                      |
| `async_flush`    | No       | `bool`     | `True`                        |

---

## Authentication

### API Keys — server-side use

Create API keys in the Olira Console or with the CLI:

```bash
olira keys create --name "my-backend" --scopes sdk:event-log api:manage-patients
```

Pass the key to `init()` or set `OLIRA_API_KEY`:

```python
olira.init(api_key="YOUR_OLIRA_API_KEY")
```

Keys are shown only once at creation. Store them in a secrets manager.

### Patient Tokens — client-side use

For patient-facing requests (e.g. from a mobile app calling the
[MCP Patient State server](https://olira.ai/api-docs) directly),
mint a short-lived patient-scoped JWT server-side. The API key used here must
carry the `sdk:patient-token` scope.

```python
token = olira.get_patient_token(patient_id="patient-uuid")
# token.access_token is a short-lived Bearer token locked to that patient
```

Pass `token.access_token` as the Bearer token from your client.
Tokens expire after `token.expires_in` seconds (default 15 minutes).

### Auth error responses

| Status | Exception         | Meaning                                  |
| ------ | ----------------- | ---------------------------------------- |
| 401    | `AuthError`       | Invalid or expired token                 |
| 403    | `AuthError`       | Token does not have the required scope   |
| 429    | `RateLimitError`  | Rate limit exceeded; check `retry_after` |
| 422    | `ValidationError` | Malformed request or payload             |
| 5xx    | `ServerError`     | Server-side failure after retries        |

---

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

---

## Scopes

| Scope                  | Description                                                    |
| ---------------------- | -------------------------------------------------------------- |
| `sdk:event-log`        | Log health events via `log()` and `log_batch()`                |
| `api:manage-patients`  | Create, read, update, delete patients                          |
| `sdk:patient-token`    | Mint patient-scoped JWTs via `get_patient_token()`             |
| `mcp:patient-state`    | Query patient state via the MCP Patient State server           |

---

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
from olira import OliraTrace, OliraEventType

# A symptom report extracted from a conversation turn
olira.log(
    event_type=OliraEventType.SYMPTOM_REPORT,
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

### `EsasItem`

Single ESAS-r symptom item (name + score 0–10).
Shape matches EsasSymptomItem in common-models util.py.
Optional type/snomed_code/meddra_code used for matching server-side.

| Field         | Required | Type  | Description                                     |
| ------------- | -------- | ----- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `name`        | Yes      | `str` | ESAS item name (display); not used for matching |
| `score`       | Yes      | `int` | Score 0–10                                      |
| `type`        | No       | `str  | None`                                           | Symptom type for matching when snomed_code and meddra_code unset (e.g. pain, nausea) (default: `None`) |
| `snomed_code` | No       | `str  | None`                                           | SNOMED CT code; first choice for matching (default: `None`)                                            |
| `meddra_code` | No       | `str  | None`                                           | MedDRA code; used when snomed_code unset (default: `None`)                                             |

### `LabResultItem`

One result item from lab_results_received.results[] (with or without LOINC).
Shape matches LabResultItem in common-models util.py.
At least one of loinc_code or test_name; at least one of value_numeric or value_string.

| Field                  | Required | Type   | Description                                                 |
| ---------------------- | -------- | ------ | ----------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `loinc_code`           | No       | `str   | None`                                                       | LOINC code when available; test_name/specimen resolved server-side (default: `None`) |
| `test_name`            | No       | `str   | None`                                                       | Required when loinc_code not provided (default: `None`)                              |
| `specimen_type`        | No       | `str   | None`                                                       | Optional when no LOINC (default: `None`)                                             |
| `test_category`        | No       | `str   | None`                                                       | e.g. hematology, metabolic, lipid (default: `None`)                                  |
| `value_numeric`        | No       | `float | None`                                                       | Quantitative result (default: `None`)                                                |
| `value_string`         | No       | `str   | None`                                                       | Non-quantitative result (default: `None`)                                            |
| `unit`                 | No       | `str`  | Unit of measure (prefer explicit e.g. g/dL) (default: `''`) |
| `abnormal_flag`        | No       | `str   | None`                                                       | H, L, N, HH, LL (default: `None`)                                                    |
| `reference_range_low`  | No       | `float | None`                                                       | — (default: `None`)                                                                  |
| `reference_range_high` | No       | `float | None`                                                       | — (default: `None`)                                                                  |
| `result_status`        | No       | `str   | None`                                                       | final, preliminary, corrected (default: `None`)                                      |

### `PerformingLab`

Performing lab from lab_results_received envelope. Shape matches common-models util.py.

| Field         | Required | Type | Description |
| ------------- | -------- | ---- | ----------- | ------------------- |
| `name`        | No       | `str | None`       | — (default: `None`) |
| `clia_number` | No       | `str | None`       | — (default: `None`) |

### `TimePeriod`

Time range in ISO 8601 datetimes. Wire-compatible with PeriodRange in common-models util.py.

| Field            | Required | Type  | Description |
| ---------------- | -------- | ----- | ----------- |
| `start_datetime` | Yes      | `str` | —           |
| `end_datetime`   | Yes      | `str` | —           |

### `OliraEventType`

`StrEnum` of all supported event types. Use these constants as `event_type`
in `log()` and `log_batch()`.

**Symptom reports**

- `OliraEventType.SYMPTOM_REPORT` → `"symptom_report"`
- `OliraEventType.SYMPTOM_FREE_TEXT` → `"symptom_free_text"`
- `OliraEventType.SYMPTOM_DETAIL` → `"symptom_detail"`
- `OliraEventType.MOODS_REPORT` → `"moods_report"`
- `OliraEventType.FUNCTIONAL_CLASS_REPORTED` → `"functional_class_reported"`
- `OliraEventType.HEALTH_METRIC_REPORTED` → `"health_metric_reported"`

**Lab & clinical**

- `OliraEventType.LAB_RESULTS_RECEIVED` → `"lab_results_received"`
- `OliraEventType.VITALS_MEASUREMENT` → `"vitals_measurement"`
- `OliraEventType.CLINICAL_NOTE_RECEIVED` → `"clinical_note_received"`
- `OliraEventType.CLINICAL_FINDING_REPORTED` → `"clinical_finding_reported"`
- `OliraEventType.PROCEDURE_RESULT_RECEIVED` → `"procedure_result_received"`
- `OliraEventType.PROCEDURE_PERFORMED` → `"procedure_performed"`
- `OliraEventType.GENOMIC_VARIANT_REPORTED` → `"genomic_variant_reported"`
- `OliraEventType.IMAGING_RESULT_RECEIVED` → `"imaging_result_received"`
- `OliraEventType.CLINICAL_MEASUREMENT_REPORTED` → `"clinical_measurement_reported"`
- `OliraEventType.TREATMENT_RESPONSE_ASSESSMENT_REPORTED` → `"treatment_response_assessment_reported"`
- `OliraEventType.CLINICAL_PLAN_ITEM_REPORTED` → `"clinical_plan_item_reported"`
- `OliraEventType.CARE_ENCOUNTER_REPORTED` → `"care_encounter_reported"`
- `OliraEventType.CARE_GOAL_REPORTED` → `"care_goal_reported"`
- `OliraEventType.IMMUNIZATION_REPORTED` → `"immunization_reported"`
- `OliraEventType.ALLERGY_INTOLERANCE_REPORTED` → `"allergy_intolerance_reported"`
- `OliraEventType.FAMILY_HISTORY_REPORTED` → `"family_history_reported"`
- `OliraEventType.DEVICE_REPORTED` → `"device_reported"`
- `OliraEventType.MEMORY_REPORT` → `"memory_report"`
- `OliraEventType.UNSTRUCTURED_REPORT_RECEIVED` → `"unstructured_report_received"`

**Questionnaires**

- `OliraEventType.QUESTIONNAIRE_RESPONSE` → `"questionnaire_response"`
- `OliraEventType.QUESTIONNAIRE_ITEM_RESPONSE` → `"questionnaire_item_response"`

**Conversations**

- `OliraEventType.CONVERSATION_COMPLETED` → `"conversation_completed"`
- `OliraEventType.CONVERSATION_TURN_LOGGED` → `"conversation_turn_logged"`

**Passive data**

- `OliraEventType.HEART_RATE_DATA_RECEIVED` → `"heart_rate_data_received"`
- `OliraEventType.SLEEP_DATA_RECEIVED` → `"sleep_data_received"`
- `OliraEventType.ACTIVITY_DATA_RECEIVED` → `"activity_data_received"`
- `OliraEventType.CGM_READING_RECEIVED` → `"cgm_reading_received"`
- `OliraEventType.SPO2_READING_RECEIVED` → `"spo2_reading_received"`
- `OliraEventType.WEIGHT_MEASUREMENT_RECEIVED` → `"weight_measurement_received"`

**Medications**

- `OliraEventType.MEDICATION_ACTION` → `"medication_action"`
- `OliraEventType.MEDICATION_DOSE_UPDATE` → `"medication_dose_update"`
- `OliraEventType.MEDICATION_ADVERSE_EVENT_REPORTED` → `"medication_adverse_event_reported"`

**Engagement**

- `OliraEventType.USER_LOGIN` → `"user_login"`
- `OliraEventType.USER_LOGOUT` → `"user_logout"`
- `OliraEventType.CONTENT_INTERACTED` → `"content_interacted"`
- `OliraEventType.NOTIFICATION_INTERACTED` → `"notification_interacted"`
- `OliraEventType.TASK_UPDATED` → `"task_updated"`
- `OliraEventType.INTERACTION_FEEDBACK` → `"interaction_feedback"`
- `OliraEventType.FEATURE_USED` → `"feature_used"`

**Profile**

- `OliraEventType.DEMOGRAPHICS_UPDATED` → `"demographics_updated"`
- `OliraEventType.CONDITION_RECORDED` → `"condition_recorded"`
- `OliraEventType.PREFERENCES_UPDATED` → `"preferences_updated"`
- `OliraEventType.EMERGENCY_CONTACT_UPDATED` → `"emergency_contact_updated"`
- `OliraEventType.CARE_TEAM_UPDATED` → `"care_team_updated"`
- `OliraEventType.INSURANCE_UPDATED` → `"insurance_updated"`
- `OliraEventType.SOCIAL_UPDATED` → `"social_updated"`
- `OliraEventType.PHARMACY_UPDATED` → `"pharmacy_updated"`
- `OliraEventType.TREATMENT_PHASE_CHANGED` → `"treatment_phase_changed"`

---

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
| ----------------- | -------- | ----- | ------- | ------ |
| `limit`           | No       | `int` | `100`   |
| `offset`          | No       | `int` | `0`     |
| `external_system` | No       | `str  | None`   | `None` |
| `external_value`  | No       | `str  | None`   | `None` |

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
| ---------------------- | -------- | ------------------------- | ------- | ------ |
| `patient_id`           | Yes      | `str`                     | —       |
| `first_name`           | No       | `str                      | None`   | `None` |
| `last_name`            | No       | `str                      | None`   | `None` |
| `email`                | No       | `str                      | None`   | `None` |
| `phone_number`         | No       | `str                      | None`   | `None` |
| `sex`                  | No       | `str                      | None`   | `None` |
| `timezone`             | No       | `str                      | None`   | `None` |
| `primary_disease_site` | No       | `str                      | None`   | `None` |
| `disease_stage`        | No       | `str                      | None`   | `None` |
| `external_identifiers` | No       | `list[ExternalIdentifier] | None`   | `None` |
| `metadata`             | No       | `dict[str, Any]           | None`   | `None` |

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
| ---------------------- | -------- | ------------------------- | ----------- | ------------------- |
| `first_name`           | No       | `str                      | None`       | — (default: `None`) |
| `last_name`            | No       | `str                      | None`       | — (default: `None`) |
| `email`                | No       | `str                      | None`       | — (default: `None`) |
| `phone_number`         | No       | `str                      | None`       | — (default: `None`) |
| `sex`                  | No       | `str                      | None`       | — (default: `None`) |
| `timezone`             | No       | `str                      | None`       | — (default: `None`) |
| `primary_disease_site` | No       | `str                      | None`       | — (default: `None`) |
| `disease_stage`        | No       | `str                      | None`       | — (default: `None`) |
| `external_identifiers` | No       | `list[ExternalIdentifier] | None`       | — (default: `None`) |
| `metadata`             | No       | `dict[str, Any]           | None`       | — (default: `None`) |

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
| -------- | -------- | ----- | ----------- | ------------------- |
| `index`  | Yes      | `int` | —           |
| `id`     | Yes      | `str` | —           |
| `source` | No       | `str  | None`       | — (default: `None`) |

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

---

## Logs

All log functions require `sdk:event-log` scope.

### Log a single event

#### `log`

```python
log(*, event_type: OliraEventType, patient_id: str, payload: dict[str, Any] | None = None, trace: OliraTrace | None = None, timestamp: str | None = None) -> None
```

Enqueue an event for background delivery. Module-level proxy to the singleton client.

| Parameter    | Required | Type             | Default |
| ------------ | -------- | ---------------- | ------- | ------ |
| `event_type` | Yes      | `OliraEventType` | —       |
| `patient_id` | Yes      | `str`            | —       |
| `payload`    | No       | `dict[str, Any]  | None`   | `None` |
| `trace`      | No       | `OliraTrace      | None`   | `None` |
| `timestamp`  | No       | `str             | None`   | `None` |

Events are enqueued and flushed in the background. Call `olira.flush()` before
process exit to ensure delivery.

**Example:**

```python
import olira
from olira import OliraEventType

olira.log(
    event_type=OliraEventType.SYMPTOM_REPORT,
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
from olira import OliraEventType, OliraTrace

# Attribute the event back to the conversation that produced it
olira.log(
    event_type=OliraEventType.SYMPTOM_REPORT,
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
from olira import LogSpec, OliraEventType

result = olira.log_batch([
    LogSpec(
        event_type=OliraEventType.VITALS_MEASUREMENT,
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
        event_type=OliraEventType.MEDICATION_DOSE_UPDATE,
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
| ----------------- | -------- | ---------------- | ----------- | ------------------- |
| `event_type`      | Yes      | `OliraEventType` | —           |
| `patient_id`      | Yes      | `str`            | —           |
| `payload`         | No       | `dict[str, Any]  | None`       | — (default: `None`) |
| `trace`           | No       | `OliraTrace      | None`       | — (default: `None`) |
| `timestamp`       | No       | `str             | None`       | — (default: `None`) |
| `idempotency_key` | No       | `str             | None`       | — (default: `None`) |

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

---

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

---

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
    olira.log(event_type=OliraEventType.SYMPTOM_REPORT, patient_id="...", payload={...})
    olira.flush()
except AuthError:
    print("Invalid or revoked API key — check your credentials")
except RateLimitError as e:
    print(f"Rate limited — retry after {e.retry_after}s")
    time.sleep(e.retry_after)
except ValidationError as e:
    print(f"Validation error: {e}")
```

---

## Common Log Payloads

### `symptom_report`

```python
olira.log(
    event_type=OliraEventType.SYMPTOM_REPORT,
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
    event_type=OliraEventType.LAB_RESULTS_RECEIVED,
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
    event_type=OliraEventType.MEDICATION_ACTION,
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
    event_type=OliraEventType.CONVERSATION_COMPLETED,
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
