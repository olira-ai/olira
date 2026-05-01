# Olira Python SDK — Requirements & Architecture Spec

**Status**: Draft for peer review
**Date**: 2026-02-26
**Location**: `packages/olira-sdk-python/`

---

## Table of Contents

1. [Context](#1-context)
2. [Authentication](#2-authentication)
3. [Public API Surface](#3-public-api-surface)
4. [Event Model](#4-event-model)
5. [Event Types & Payload Schemas](#5-event-types--payload-schemas)
6. [API Endpoints](#6-api-endpoints)
7. [Delivery & Reliability](#7-delivery--reliability)
8. [Error Handling](#8-error-handling)
9. [Privacy & Compliance Defaults](#9-privacy--compliance-defaults)
10. [Packaging & Distribution](#10-packaging--distribution)
11. [Patient Management](#11-patient-management)
12. [Patient Token](#12-patient-token)
13. [Future Features](#13-future-features)
14. [Appendix: Full Event Catalogue](#appendix-full-event-catalogue)

---

## 1. Context

Olira's platform ingests patient-related data from customer applications and uses it to build a **Patient State** — a structured, continuously-updated model of each patient's health context. Customers currently have no standardised way to push data into the platform programmatically. This SDK is the ingestion client for that use case.

The spec draws on patterns from:

- **Braintrust SDK** — explicit batch size control, separate sync/async clients, structured retry exceptions
- **Sentry SDK** — single `init()` entry point, non-blocking background queue, scope-enriched context

Authentication reuses the existing API key infrastructure: keys are created via the Olira CLI (`olira keys create`) or Console dashboard, stored in the customer's own secrets manager, and verified server-side against `McpApiKeyDocument` hashes.

---

## 2. Authentication

### Model

- Opaque Olira API keys only (v1). No JWT/Auth0.
- Keys are scoped to a single tenant/organisation.
- Created via `olira keys create --name "..."` (CLI) or Console dashboard.
- Key lifecycle (create / list / revoke) is already implemented in `services/app-api/routes/auth/api_keys.py`.
- Key format: `olira_{env}_{64-hex-chars}` (e.g. `olira_prod_…`, `olira_dev_…`; prefix stored for display; hash stored server-side).

### SDK-side Behaviour

- Accept key via:
  1. `olira.init(api_key="olira_prod_...")` — explicit
  2. `OLIRA_API_KEY` environment variable — fallback
- Key is **never logged** (redacted as `olira_***` in all debug output).
- Included in every HTTP request as `Authorization: Bearer olira_{env}_{key}`.

### Environment

```python
from enum import StrEnum

class OliraEnv(StrEnum):
    PRODUCTION  = "production"
    DEVELOPMENT = "development"
```

`OliraEnv.PRODUCTION` is the default. Use `OliraEnv.DEVELOPMENT` for local development, CI, and staging systems — Olira will route these events away from live Patient State.

---

## 3. Public API Surface

### Module-level (singleton)

```python
import olira
from olira import OliraLogType, OliraTrace

# Minimal — only the API key is required
olira.init(api_key="olira_prod_...")   # or set OLIRA_API_KEY env var

# Minimal log — payload is a free-form dict
olira.log(
    log_type=OliraLogType.SYMPTOM_REPORT,
    patient_id="p_123",
    payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 4}]},
)

# With trace (links event to an internal Olira object)
olira.log(
    log_type=OliraLogType.CONVERSATION_COMPLETED,
    patient_id="p_123",
    trace=OliraTrace(object_type="conversation", object_id="conv_789"),
    payload={"duration_seconds": 142},
)

olira.flush()
```

Pydantic helpers remain exported for customers who want structured payload construction with client-side validation:

```python
from olira import EsasItem

payload = {
    "instrument": "esas_r",
    "symptoms": [EsasItem(name="pain", score=4).model_dump()],
}
olira.log(log_type=OliraLogType.SYMPTOM_REPORT, patient_id="p_123", payload=payload)
```

Optional `init` parameters:

| Parameter      | Default                       | Why you'd set it                                                                                                                                                                                        |
| -------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `environment`  | `OliraEnv.PRODUCTION`         | Set to `OliraEnv.DEVELOPMENT` when sending from non-production systems. Olira routes events server-side based on this value — no URL change required.                                                   |
| `service_name` | `None`                        | Name of the calling service (e.g. `"emr-integration"`, `"care-api"`). Useful for attribution and debugging when multiple services in your stack write to Olira. Single-backend customers can omit this. |
| `base_url`     | `"https://api.prod.olira.ai"` | Override only if directed by Olira support (e.g. pointing at a sandbox). Most customers never set this.                                                                                                 |
| `async_flush`  | `True`                        | Set to `False` to disable the background thread and flush synchronously on every `log()` call. Use in serverless / Lambda environments where a background thread cannot persist between invocations.    |

### Explicit class (multi-tenant / dependency injection)

`olira.init()` creates a single `OliraClient` and stores it as a module-level singleton. Every `olira.log()` call proxies to it. This covers the common case: a single-tenant backend service with one API key shared across the whole process.

Use `OliraClient` directly when you need more than one instance:

- **Multi-tenant** — different customers have different API keys, so you need one client per key.
- **Dependency injection / testing** — pass the client into a class constructor so it can be swapped for a mock in tests, without touching global state.
- **Different configurations** — e.g. one client with `async_flush=False` for a Lambda handler and another with a longer timeout for a batch job.

```python
from olira import OliraClient, OliraEnv, OliraLogType

# Minimal
client = OliraClient(api_key="olira_prod_...")

# With optional parameters
client = OliraClient(
    api_key="olira_prod_...",
    environment=OliraEnv.DEVELOPMENT,  # isolate non-prod data from Patient State
    service_name="emr-service",  # tag which service is writing events
    batch_size=50,
    flush_interval=1.5,
    max_queue_size=10_000,
    timeout=5.0,
    max_retries=3,
    on_error="drop",
    async_flush=True,  # set False for serverless / Lambda
)

# Single event via log()
client.log(
    log_type=OliraLogType.LAB_RESULTS_RECEIVED,
    patient_id="p_456",
    payload={"results": [{"loinc_code": "718-7", "unit": "g/dL", "value_numeric": 11.2}]},
)
client.flush()
```

### Async Client

```python
from olira import AsyncOliraClient, OliraLogType

async with AsyncOliraClient(api_key=...) as client:
    await client.log(
        log_type=OliraLogType.SYMPTOM_REPORT,
        patient_id="p_789",
        payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 3}]},
    )
    await client.flush()
```

`AsyncOliraClient` provides the same `log()` / `log_batch()` interface as `OliraClient` with `async def` signatures. Included in v1.

### Explicit batch — `log_batch()`

For bulk submissions where the caller already has a list of events. Sends a single `/v1/logs/batch` request directly, **bypassing the background queue**, and returns a `BatchResult`.

```python
from olira import LogSpec, BatchResult, OliraLogType

result: BatchResult = olira.log_batch([
    LogSpec(log_type=OliraLogType.USER_LOGIN, patient_id="p_1"),
    LogSpec(log_type=OliraLogType.LAB_RESULTS_RECEIVED, patient_id="p_2",
              payload={"results": [...]}),
    LogSpec(log_type=OliraLogType.SYMPTOM_REPORT, patient_id="p_3",
              payload={"instrument": "esas_r", "symptoms": [...]}),
])

print(result.accepted)           # int
print(result.failed)             # int
for err in result.errors:
    print(err.index, err.code, err.message)
```

**Exported types:**

| Name             | Kind      | Description                                                           |
| ---------------- | --------- | --------------------------------------------------------------------- |
| `OliraLogType` | StrEnum   | customer-facing log types    |
| `OliraTrace`     | BaseModel | Links event to an internal Olira object (`object_type` + `object_id`) |
| `LogSpec`        | dataclass | Lightweight log spec for `log_batch()`                                |
| `BatchResult`    | dataclass | Result of `log_batch()` — `accepted`, `failed`, `errors`              |
| `BatchError`     | dataclass | Per-event error from a batch response                                 |
| `EsasItem`       | BaseModel | Pydantic helper for ESAS-r symptom payload construction               |
| `LabResultItem`  | BaseModel | Pydantic helper for lab results payload construction                  |
| `PerformingLab`  | BaseModel | Pydantic helper for performing lab in lab results                     |
| `TimePeriod`     | BaseModel | ISO 8601 time range (start/end)                                       |

---

## 4. Log model

### Required Fields (every log)

| Field        | Type             | Notes                                                                        |
| ------------ | ---------------- | ---------------------------------------------------------------------------- |
| `log_type` | `OliraLogType` | Derived from `OliraLogType.value`; customers pass `log_type=` to `log()` (serialized as `log_type` on the wire) |
| `patient_id` | `str`            | The Olira-assigned `id` returned when you created the patient. See [Patient ID Resolution](#patient-id-resolution) below. |

### Optional Fields

| Field             | Type              | Default              | Notes                                   |
| ----------------- | ----------------- | -------------------- | --------------------------------------- |
| `timestamp`       | ISO 8601 `str`    | Server time          | Client-provided timestamp               |
| `payload`         | `dict[str, JSON]` | `{}`                 | Free-form event payload                 |
| `trace`           | `OliraTrace`      | `None`               | Links event to an internal Olira object |
| `idempotency_key` | `str`             | Auto-generated UUID4 | See note below                          |
| `log_id`            | `str`             | Auto-generated UUID4 | Client-generated log identifier (`log_id` on the wire)       |

#### `idempotency_key`

The SDK auto-generates a UUID4 per event. **For `log()` users this field is invisible and irrelevant** — the background worker retries the same in-memory Event object (same key) automatically, so deduplication is handled transparently.

**`log_batch()` callers must be mindful.** `log_batch()` bypasses the background queue — the caller owns the retry loop. If the process crashes after a failed send, the `LogSpec` objects are gone. Replaying from a persistent queue or DB constructs new `LogSpec` objects with new auto-generated keys, and the server will store duplicates.

**Fix for replay scenarios:** derive a stable key from your source record so the same record always produces the same key across process restarts:

```python
client.log_batch([
    LogSpec(
        log_type=OliraLogType.LAB_RESULTS_RECEIVED,
        patient_id="p_123",
        payload={...},
        idempotency_key=f"lab-result-{db_record.id}",  # stable, derived from source
    ),
])
```

Relevant for: outbox pattern, event replay pipeline, bulk historical backfill — any system that persists events to a queue or DB before sending and replays on failure. If you are not doing this, the auto-generated key is correct.

### `OliraTrace` Fields

| Field         | Type  | Notes                              |
| ------------- | ----- | ---------------------------------- |
| `object_type` | `str` | e.g. `"conversation"`, `"message"` |
| `object_id`   | `str` | Internal Olira object ID           |

### Context Block (auto-injected by SDK)

```json
{
  "context": {
    "environment": "production",
    "service": "customer-backend",
    "sdk_version": "0.1.0",
    "sdk_language": "python"
  }
}
```

### Wire Format (single event)

**Minimal** — `olira.log(log_type=OliraLogType.USER_LOGIN, patient_id="p_abc")`:

```json
{
  "log_type": "user_login",
  "patient_id": "p_abc",
  "log_id": "e1a2b3c4-...",
  "idempotency_key": "c6f8b1...",
  "payload": {},
  "context": {
    "environment": "production",
    "service": "",
    "sdk_version": "0.1.0",
    "sdk_language": "python"
  }
}
```

`timestamp` is omitted when not supplied — the server uses ingestion time. `trace` is omitted when `None`.

**With payload and trace** — `olira.log(log_type=OliraLogType.CONVERSATION_COMPLETED, patient_id="p_abc", payload={...}, trace=OliraTrace(...))`:

```json
{
  "log_type": "conversation_completed",
  "patient_id": "p_abc",
  "timestamp": "2026-02-26T08:15:00Z",
  "log_id": "e1a2b3c4-...",
  "idempotency_key": "c6f8b1...",
  "payload": {
    "duration_seconds": 142
  },
  "trace": {
    "object_type": "conversation",
    "object_id": "conv_789"
  },
  "context": {
    "environment": "production",
    "service": "customer-backend",
    "sdk_version": "0.1.0",
    "sdk_language": "python"
  }
}
```

`payload` maps directly to the `payload` argument of `log()`. `log_id` and `idempotency_key` are auto-generated UUID4s.

### How SDK wire fields map to internal EventLog documents

The ingestion endpoint translates wire fields into the internal `EventLog` document schema. The mapping is not 1-to-1:

| SDK wire field    | `EventLog` field  | Notes                                                                                                                     |
| ----------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `log_type`        | `type`            | Ingestion endpoint maps the string value to the `EventLogType` enum                                                       |
| `patient_id`      | `user_id`         | Resolved server-side via `PatientUser._id` (ObjectId) lookup scoped to the calling organisation |
| `payload`         | `payload`         | Direct pass-through                                                                                                       |
| `trace`           | `trace`           | Direct; `object_type` string is mapped to `ObjectType` enum                                                               |
| `timestamp`       | `timestamp`       | Event occurrence time. Client-provided; server substitutes ingestion time when absent (see caveat below)                  |
| `log_id`          | `event_id`        | Customer-facing UUID4 on the wire (`log_id`); stored as `event_id` on the document.                                                               |
| `idempotency_key` | _(not persisted)_ | `EventLogBase` currently has no `idempotency_key` field — server-side deduplication is not yet implemented                |
| _(server-set)_    | `ingested_at`     | Server ingestion timestamp. Always set at insert time; never accepted from the wire payload                               |

The `EventLog` document gets a MongoDB `_id` (ObjectId) assigned by Beanie on insert. This is the server's internal record identifier and is never exposed in the public SDK API. Use the wire `log_id` (persisted as `event_id`) to reference logs externally.

**`timestamp` caveat:** `timestamp` is the event occurrence time (when the thing happened in the real world). If the SDK caller does not provide it, the server falls back to ingestion time — so `timestamp` and `ingested_at` will be identical.

### Patient ID Resolution

`patient_id` in every SDK method is the **Olira-assigned `id`** returned when you called `create_patient()` (the `id` field of the `Patient` response). You do not supply this id at creation time — Olira assigns it at creation.

```python
# patient_id is always the Olira-assigned id returned by create_patient():
patient = client.create_patient(first_name="Jane", last_name="Smith", ...)
olira.log(log_type=OliraLogType.USER_LOGIN, patient_id=patient.id)
```

Patients must be created via `create_patient()` (or the Console) before events can be logged against them. Store the returned `id` from `create_patient()` — it is the value you use in `log()` and all other calls.

### patient_id Validation

The SDK raises `olira.ValidationError` before any network call if `patient_id`:

- Is empty or whitespace.
- Matches a known PII pattern: email address (`@` domain), US phone (`\d{10}`), or US SSN (`\d{3}-\d{2}-\d{4}`).

Customers are responsible for pseudonymisation. The SDK documentation clearly warns against sending direct patient identifiers.

---

## 5. Event Types & Payload Schemas

Customers call `olira.log(log_type=OliraLogType.X, patient_id=..., payload={...})` for all log types. The `payload` is a free-form `dict` — structure is defined per log type below and validated server-side (HTTP 422 on mismatch).

**Validation strategy:**

- `patient_id` PII guard and 512 KB payload limit are enforced client-side (raise `ValidationError` before any network call).
- `log_type` must be a valid `OliraLogType` — enforced by the enum type annotation.
- Payload structure is **not** validated client-side. Customers who want pre-validation can use the exported Pydantic helper models (e.g. `EsasItem`, `LabResultItem`) to construct and validate payloads, then call `.model_dump()` before passing to `log()`.

**Schema source of truth:** Payload shapes align with `packages/common-models/src/olira_common_models/schemas/personalization/util.py`. The SDK does not depend on common-models so it remains public and PyPI-installable; it defines compatible Pydantic models locally.

### 5.1 Symptom Reports

| Event type                  | Payload fields (required / optional)                                                                                  |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `SYMPTOM_REPORT`            | `instrument: str`, `symptoms: list[EsasItem\|CtcaeItem\|CustomSymptomItem]` — `recall_period?: str`, `recall_period_days?: int` |
| `SYMPTOM_FREE_TEXT`         | `text: str` — `associated_symptoms?: list[str]`                                                                       |
| `SYMPTOM_DETAIL`            | `type: str`, `detail_type: str`, `response: str` — `question?: str`, `snomed_code?: str`, `meddra_code?: str`        |
| `FUNCTIONAL_CLASS_REPORTED` | `instrument: str`, `functional_class: int` — `reported_by?: str`, `change_from_prior?: dict`                          |
| `HEALTH_METRIC_REPORTED`    | `metric_type: str`, `score: float`, `scale_min: float`, `scale_max: float` — `source?: str`                           |
| `MOODS_REPORT`              | `moods: list[MoodItem]` — `source?: str`                                                                              |

**Pydantic helpers (exported from `olira`):**

```python
from pydantic import BaseModel, Field

class EsasItem(BaseModel):
    """Shape matches EsasSymptomItem in common-models util.py."""
    name: str                      # pain, tiredness, nausea, depression, anxiety, ...
    score: int = Field(ge=0, le=10)
    type: str | None = Field(default=None)  # for matching when snomed/meddra unset
    snomed_code: str | None = None
    meddra_code: str | None = None
```

**Example:**

```python
from olira import EsasItem, OliraLogType

items = [EsasItem(name="pain", score=4), EsasItem(name="nausea", score=2), EsasItem(name="anxiety", score=5)]
payload = {"instrument": "esas_r", "symptoms": [i.model_dump() for i in items], "recall_period": "past_24h"}

client.log(log_type=OliraLogType.SYMPTOM_REPORT, patient_id="p_abc123", payload=payload)
```

### 5.2 Lab & Clinical

| Event type               | Payload fields (required / optional)                                                                                                                                                                                 |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `LAB_RESULTS_RECEIVED`   | `results: list[LabResultItem]` — `panel_name?: str`, `panel_loinc_code?: str`, `collection_datetime?: str`, `ordered_by_npi?: str`, `ordering_provider_name?: str`, `performing_lab?: PerformingLab`, `source?: str` |
| `VITALS_MEASUREMENT`     | `measurements: VitalsMeasurements`, `source: str` — `collection_datetime?: str`                                                                                                                                      |
| `CLINICAL_NOTE_RECEIVED` | `note_type: str`, `source: str` — `text?: str`, `sections?: list[dict]`, `loinc_code?: str`, `authored_by?: dict`, `authored_date?: str`, `encounter_id?: str`                                                       |

**Pydantic helpers:**

```python
class LabResultItem(BaseModel):
    loinc_code: str | None = None
    test_name: str | None = None       # required when loinc_code absent
    specimen_type: str | None = None
    test_category: str | None = None   # 'hematology'|'metabolic'|'lipid'|...
    value_numeric: float | None = None
    value_string: str | None = None    # at least one of value_numeric/value_string required
    unit: str = ""
    abnormal_flag: str | None = None   # 'H'|'L'|'N'|'HH'|'LL'
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    result_status: str | None = None   # 'final'|'preliminary'|'corrected'

class PerformingLab(BaseModel):
    name: str | None = None
    clia_number: str | None = None
```

**Example:**

```python
from olira import LabResultItem, PerformingLab, OliraLogType

result = LabResultItem(loinc_code="718-7", test_name="Hemoglobin", value_numeric=11.2, unit="g/dL", abnormal_flag="L")
payload = {
    "results": [result.model_dump(exclude_none=True)],
    "panel_name": "CBC",
    "collection_datetime": "2026-02-26T07:30:00Z",
    "performing_lab": PerformingLab(name="Acme Lab").model_dump(exclude_none=True),
}
client.log(log_type=OliraLogType.LAB_RESULTS_RECEIVED, patient_id="p_abc123", payload=payload)
```

### 5.3 Questionnaires

| Event type                    | Payload fields (required / optional)                                                                                                                                |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `QUESTIONNAIRE_RESPONSE`      | `instrument_id: str`, `instrument_type: str`, `items: list[dict]`, `scores: dict` — `instrument_version?: str`, `recall_period_days?: int`, `administration?: dict` |
| `QUESTIONNAIRE_ITEM_RESPONSE` | `question: str`, `response_value` — `response_scale_max`, `response_label?: str`, `instrument_id?: str`, `item_number?: int`, `context?: str`                       |

### 5.4 Conversations

| Event type                 | Payload fields (required / optional)                                                                                                                |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CONVERSATION_COMPLETED`   | — `conversation_id?: str`, `channel?: str`, `duration_seconds?: int`, `language?: str`, `participants?: list[dict]`, `transcript?: str\|list[dict]` |
| `CONVERSATION_TURN_LOGGED` | `conversation_id: str`, `turn_index: int`, `speaker_label: str`, `text: str` — `channel?: str`                                                      |

**Note on transcript patterns:** Either (1) send full transcript in `CONVERSATION_COMPLETED`, or (2) send incremental turns via `CONVERSATION_TURN_LOGGED` and then `CONVERSATION_COMPLETED` without a transcript. Do not mix patterns for the same conversation.

**Example:**

```python
from olira import OliraLogType, OliraTrace

trace = OliraTrace(object_type="conversation", object_id="conv_789")
payload = {
    "channel": "in_app_chat",
    "duration_seconds": 142,
    "transcript": [
        {"speaker_label": "agent", "text": "How are you feeling today?", "turn_index": 0},
        {"speaker_label": "patient", "text": "A bit tired, pain is around a 4.", "turn_index": 1},
    ],
}
client.log(log_type=OliraLogType.CONVERSATION_COMPLETED, patient_id="p_abc123", payload=payload, trace=trace)
```

### 5.5 Passive Data

| Event type                    | Payload fields (required / optional)                                                                                                                                |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `HEART_RATE_DATA_RECEIVED`    | `period: dict`, `device_provider: str` — `resting_bpm?`, `avg_bpm?`, `min_bpm?`, `max_bpm?`, `avg_hrv_sdnn_ms?`, `irregular_events_count?`                          |
| `SLEEP_DATA_RECEIVED`         | `period: dict`, `device_provider: str` — `total_sleep_minutes?`, `deep_sleep_minutes?`, `rem_sleep_minutes?`, `light_sleep_minutes?`, `awake_minutes?`              |
| `ACTIVITY_DATA_RECEIVED`      | `period: dict`, `device_provider: str` — `steps?`, `walking_minutes?`, `active_minutes?`, `sedentary_minutes?`, `calories_total?`, `exercise_sessions?: list[dict]` |
| `CGM_READING_RECEIVED`        | `glucose_mg_dl: float`, `sensor_timestamp: str`, `device_provider: str` — `trend_arrow?: str`, `glucose_flag?: str`                                                 |
| `SPO2_READING_RECEIVED`       | `spo2_percent: float`, `sensor_timestamp: str`, `device_provider: str` — `pulse_bpm?: float`, `measurement_context?: str`                                           |
| `WEIGHT_MEASUREMENT_RECEIVED` | `weight_kg: float`, `sensor_timestamp: str`, `device_provider: str` — `body_fat_percent?: float`, `bmi?: float`                                                     |

`period` is a dict with `start_datetime` and `end_datetime` (ISO 8601). Use `TimePeriod.model_dump()` to construct it.

**Example:**

```python
from olira import TimePeriod, OliraLogType

payload = {
    **TimePeriod(start_datetime="2026-02-25T22:10:00Z", end_datetime="2026-02-26T06:45:00Z").model_dump(),
    "device_provider": "withings",
    "total_sleep_minutes": 395,
    "deep_sleep_minutes": 72,
    "rem_sleep_minutes": 88,
    "awake_minutes": 20,
}
client.log(log_type=OliraLogType.SLEEP_DATA_RECEIVED, patient_id="p_abc123", payload=payload)
```

### 5.6 Medication

| Event type                          | Payload fields (required / optional)                                                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `MEDICATION_ACTION`                 | `action: 'add'\|'update'\|'delete'`, `medications: list[dict]` (see MedicationItem / MedicationPatch / MedicationIdentifier schema) |
| `MEDICATION_DOSE_UPDATE`            | `medication_adherence: list[DoseRecord]` — `source?: str`                                                                               |
| `MEDICATION_ADVERSE_EVENT_REPORTED` | `rxnorm_cui?: str`, `medication_name?: str`, `adverse_event: str` — `severity?: str`, `onset_date?: str`, `resolved?: bool`             |

**Medication identity:** `rxnorm_cui` is the preferred identifier. When provided, `medication_name` and `therapeutic_class` are resolved server-side. At least one of `rxnorm_cui` or `medication_name` must be present.

**Example:**

```python
from olira import OliraLogType

payload = {
    "action": "add",
    "medications": [{
        "rxnorm_cui": "1049502",
        "medication_name": "Ondansetron 4mg",
        "dose": 4.0,
        "dose_unit": "mg",
        "frequency": "every_8h_as_needed",
        "route": "oral",
        "form": "tablet",
        "start_date": "2026-02-26",
    }]
}
client.log(log_type=OliraLogType.MEDICATION_ACTION, patient_id="p_abc123", payload=payload)
```

### 5.7 Engagement

| Event type                | Payload fields (required / optional)                                                                                                |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `USER_LOGIN`              | —                                                                                                                                   |
| `USER_LOGOUT`             | —                                                                                                                                   |
| `CONTENT_INTERACTED`      | `content_type: str`, `action: str` — `content_id?: str`, `title?: str`, `preview?: str`, `dwell_time_seconds?: int`, `reason?: str` |
| `NOTIFICATION_INTERACTED` | `notification_type: str`, `action: str` — `delivered_at?: str`, `time_to_open_seconds?: int`                                        |
| `TASK_UPDATED`            | `task_type: str`, `action: str` — `task_id?: str`, `task_description?: str`, `completion_time_seconds?: int`                        |
| `INTERACTION_FEEDBACK`    | `target_type: str`, `feedback_type: str` — `target_id?: str`                                                                        |
| `FEATURE_USED`            | `feature_name: str` — `session_id?: str`, `dwell_time_seconds?: int`                                                                |

**Example:**

```python
from olira import OliraLogType

client.log(
    log_type=OliraLogType.FEATURE_USED,
    patient_id="p_abc123",
    payload={"feature_name": "symptom_tracker", "session_id": "sess_001", "dwell_time_seconds": 45},
)
```

### 5.8 Profile & Stable Data

All profile events are patch-style: include only the fields that changed. Omitted fields are left untouched server-side.

| Event type                  | Payload fields (required / optional)                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `DEMOGRAPHICS_UPDATED`      | — `name?`, `dob?`, `sex?`, `marital_status?`, `address?`, `phone?`, `email?`, `language?`, `ethnicity?`        |
| `CONDITION_UPDATED`         | — `disease_type?`, `stage?`, `diagnosis_date?`, `icd10_codes?: list[str]`                                      |
| `PREFERENCES_UPDATED`       | — `reading_level?`, `tone?`, `dietary_preferences?`, `comfort_with_technology?`, `notification_preferences?`   |
| `EMERGENCY_CONTACT_UPDATED` | — `name?`, `relationship?`, `phone?`, `email?`                                                                 |
| `CARE_TEAM_UPDATED`         | `members: list[dict]` (action, role, name, npi, organization)                                                  |
| `INSURANCE_UPDATED`         | — `payer?`, `plan_name?`, `member_id?`, `group_id?`                                                            |
| `SOCIAL_UPDATED`            | — `living_situation?`, `support_system?`, `transportation_access?`, `employment_status?`, `housing_stability?` |
| `PHARMACY_UPDATED`          | — `name?`, `address?`, `phone?`                                                                                |
| `TREATMENT_PHASE_CHANGED`   | `new_phase: str`, `effective_date: str`, `changed_by: str` — `previous_phase?: str`                            |

**Example:**

```python
from olira import OliraLogType

client.log(
    log_type=OliraLogType.DEMOGRAPHICS_UPDATED,
    patient_id="p_abc123",
    payload={"dob": "1972-04-15", "sex": "female", "language": "en"},
)
```

---

## 6. API Endpoints

The SDK targets the `app-api` surface via a dedicated SDK router at `services/app-api/routes/sdk/`.

Organisation identity is derived entirely from the API key — every request carries `Authorization: Bearer olira_{env}_{key}` and the server resolves the org server-side. Customers never include an `org_id` in the payload.

### 6.1 Full Endpoint Table

| Method   | Path                        | Purpose                                     | Required scope        |
| -------- | --------------------------- | ------------------------------------------- | --------------------- |
| `POST`   | `/v1/logs/batch`            | Batch of up to `batch_size` events          | `sdk:event-log`       |
| `POST`   | `/v1/patients`              | Create a patient                            | `api:manage-patients` |
| `GET`    | `/v1/patients`              | List patients (paginated)                   | `api:manage-patients` |
| `GET`    | `/v1/patients/{patient_id}` | Get a patient by id                         | `api:manage-patients` |
| `PUT`    | `/v1/patients/{patient_id}` | Update a patient (partial)                  | `api:manage-patients` |
| `DELETE` | `/v1/patients/{patient_id}` | Soft-delete a patient                       | `api:manage-patients` |
| `POST`   | `/v1/auth/token`            | Mint a patient-scoped JWT                   | `sdk:patient-token`   |

`{patient_id}` in patient paths is the customer-supplied `id` — never a MongoDB ObjectId.

### Batch Request (`POST /v1/logs/batch`)

```json
{ "logs": [ ... ] }
```

### Batch Response

```json
{
  "accepted": 48,
  "failed": 2,
  "errors": [
    {
      "index": 3,
      "code": "validation_error",
      "message": "patient_id required"
    }
  ]
}
```

Partial batch failures: the SDK logs dropped events (log_type only, no payload content) and invokes the `on_error` callback if configured.

> **Note — patient graph update:** `PatientUser` records created via the Console API or SDK receive a `UserPatientState` at creation time (`create_default_patient_state()` is called as part of the `PatientUser` lifecycle). Events are saved to the `EventLog` collection and the graph pipeline runs normally.

### Create Patient (`POST /v1/patients`)

Request body:

```json
{
  "first_name": "Jane",
  "last_name": "Smith",
  "email": "jane@example.com",
  "phone_number": "+15550001234",
  "date_of_birth": "1985-03-22T00:00:00Z",
  "sex": "female",
  "timezone": "America/New_York",
  "primary_disease_site": "breast",
  "disease_stage": "II"
}
```

- The server assigns a stable `id` at creation time; it is returned in the response.
- Returns `201` with the created patient as a `SdkPatientResponse` body.

### List Patients (`GET /v1/patients`)

Query params: `limit` (1–100, default 100), `offset` (default 0).

Response:

```json
{
  "patients": [
    {
      "id": "mrn-00042",
      "first_name": "Jane",
      "last_name": "Smith",
      "sex": "female",
      "timezone": "America/New_York",
      "status": "pending",
      "primary_disease_site": "breast",
      "disease_stage": "II",
      "created_at": "2026-03-01T12:00:00+00:00"
    }
  ],
  "total": 1,
  "has_more": false
}
```

Deleted patients are excluded. Only patients created via the SDK (i.e. with an `id`) are returned.

### Get / Update / Delete Patient

`GET /v1/patients/{patient_id}` — returns a single `SdkPatientResponse`.

`PUT /v1/patients/{patient_id}` — partial update. Supply only the fields to change:

```json
{ "disease_stage": "III" }
```

`DELETE /v1/patients/{patient_id}` — soft-delete. Sets status to `deleted`; the `id` is permanently reserved. Returns `{ "ok": true }`.

All three return `404` if the patient does not exist or has already been deleted.

### Mint Patient Token (`POST /v1/auth/token`)

Request body:

```json
{ "patient_id": "mrn-00042" }
```

`patient_id` is the customer-supplied id (same as everywhere else in the SDK). The server resolves it to the internal PatientUser and mints a short-lived RS256 JWT locked to that patient.

Response:

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "scopes": ["mcp:patient-state"]
}
```

- TTL: 900 seconds (15 minutes).
- The JWT carries `user_type: "patient"` and `patient_id` locked to the internal ObjectId — the MCP Patient State server enforces this and ignores any `patient_id` passed in tool arguments.
- Returns `404` if the patient does not exist.

---

## 7. Delivery & Reliability

### Default: Non-Blocking Background Queue (`log()`)

When you call `log()`, the event is placed onto an in-memory queue and the call returns immediately — your application code is never blocked waiting for a network request. A background thread runs continuously alongside your process, draining that queue by batching events and sending them to the Olira API.

The background thread sends a batch when either of these conditions is met:

- The queue has accumulated `batch_size` events (default 50), or
- `flush_interval` seconds have passed since the last send (default 1.5s).

This means a single `log()` call doesn't trigger an HTTP request on its own — events are grouped and sent together, which keeps network overhead low regardless of how frequently your code calls `log()`.

**Queue backpressure:** the queue is bounded at `max_queue_size` events (default 10,000). If your code produces events faster than the background thread can drain them and the queue fills up, new events are dropped and the `on_error` handler is invoked. This is intentional — the SDK never blocks the caller and never consumes unbounded memory.

**Best-effort delivery:** failed requests are retried up to `max_retries` times (default 3) with exponential backoff. After all retries are exhausted the event is permanently dropped and `on_error` is invoked.

### `flush()`

`flush()` is a **blocking** call that waits until every event currently in the queue has been delivered (or permanently failed) before returning. You need this in two situations:

1. **End of a short-lived script** — without `flush()` the process exits and in-flight events are lost. The SDK registers an `atexit` hook that calls `flush()` automatically on normal interpreter shutdown, so most scripts are covered without any extra code.
2. **Tests and CI** — call `flush()` after your test code to ensure all events have been sent before making assertions.

```python
olira.log(log_type=OliraLogType.USER_LOGIN, patient_id="p_123")
olira.flush()  # blocks until the event above has been delivered
```

### Serverless / `async_flush=False`

The background thread cannot persist between invocations in serverless environments (AWS Lambda, Cloud Run, etc.) because each invocation gets a fresh process. Set `async_flush=False` to disable the background thread entirely — `log()` then sends synchronously on every call, blocking until the HTTP request completes.

```python
client = OliraClient(api_key=..., async_flush=False)
client.log(...)  # blocks until delivered — no background thread
```

### Explicit Batch (`log_batch()`)

`log_batch()` bypasses the background queue entirely and sends a single `POST /v1/logs/batch` request synchronously, returning a `BatchResult`.

```python
from olira import LogSpec, BatchResult, OliraLogType

result: BatchResult = client.log_batch([
    LogSpec(log_type=OliraLogType.USER_LOGIN, patient_id="p_1"),
    LogSpec(log_type=OliraLogType.SYMPTOM_REPORT, patient_id="p_2",
              payload={"instrument": "esas_r", "symptoms": [...]}),
])
# result.accepted: number of events accepted server-side
# result.failed:   number rejected
# result.errors:   list of BatchError(index, code, message) for rejected events
```

Use `log_batch()` when:

- Bulk-ingesting historical data.
- Sending a set of events that should succeed or fail together.
- An idempotent retry loop where you need per-event error details.

`log_batch()` still validates `patient_id` (PII guard) and payload size per event client-side before sending.

### Configuration Defaults

| Setting          | Default  | Description                                             |
| ---------------- | -------- | ------------------------------------------------------- |
| `batch_size`     | `50`     | Max events per HTTP request                             |
| `flush_interval` | `1.5` s  | Periodic background flush interval                      |
| `max_queue_size` | `10_000` | Backpressure limit before dropping                      |
| `timeout`        | `5.0` s  | HTTP request timeout                                    |
| `max_retries`    | `3`      | Retry attempts on transient failures                    |
| `on_error`       | `"drop"` | `"drop"` / `"raise"` / callable                         |
| `async_flush`    | `True`   | `False` disables background thread (serverless pattern) |

### Retry Policy

| Condition                  | Behaviour                          |
| -------------------------- | ---------------------------------- |
| Network error, DNS failure | Retry                              |
| `408 Request Timeout`      | Retry                              |
| `429 Too Many Requests`    | Retry; honour `Retry-After` header |
| `5xx Server Error`         | Retry                              |
| `400 Bad Request`          | Drop — permanent failure           |
| `401 Unauthorized`         | Drop — raise `AuthError`           |
| `403 Forbidden`            | Drop — raise `AuthError`           |
| `404 Not Found`            | Drop — permanent failure           |
| `422 Unprocessable Entity` | Drop — permanent failure           |

---

## 8. Error Handling

### Typed Exception Hierarchy

```
OliraError (base)
├── AuthError          # 401/403 — invalid or revoked API key
├── RateLimitError     # 429 — includes retry_after: int attribute
├── ValidationError    # 422 / client-side — malformed event
├── ServerError        # 5xx — server-side failure
└── NetworkError       # Connection timeout, DNS failure
```

```python
import olira

try:
    client.log(log_type=olira.OliraLogType.SYMPTOM_REPORT, patient_id="p_123",
               payload={"instrument": "esas_r", "symptoms": [olira.EsasItem(name="pain", score=4).model_dump()]})
except olira.RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
except olira.ValidationError as e:
    print(f"Bad event: {e}")
```

### Error Modes

| Mode                        | Behaviour                                                                                                            |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `on_error="drop"` (default) | All errors caught internally. Failed events silently dropped after max retries. SDK never raises into customer code. |
| `on_error="raise"`          | Exceptions propagate to the caller. Useful for CI pipelines where event loss is unacceptable.                        |
| `on_error=callback`         | Customer receives `(error: OliraError, events: list[dict]) -> None`. Use for custom dead-letter queue handling.      |

---

## 9. Privacy & Compliance Defaults

Given the healthcare context, the SDK enforces these defaults.

### 9.1 SDK-side (customer's environment)

These controls govern what the SDK writes into the customer's own log pipeline (e.g. CloudWatch, Datadog). PHI must never appear there.

| Concern                | Behaviour                                                                                                                                                                                                                                                                                                                                |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Payload logging        | Event bodies are **never** written to logs. Only `log_type`, first 8 chars of `patient_id`, and batch metadata logged at `DEBUG` level via the standard Python `logging` module under the logger name `olira`. Silence or redirect with standard Python logging config.                                                                |
| API key redaction      | Keys always masked as `olira_***` in all output.                                                                                                                                                                                                                                                                                         |
| `patient_id` PII guard | `ValidationError` raised if value matches email, 10-digit phone, or SSN pattern.                                                                                                                                                                                                                                                         |
| Max payload size       | 512 KB per event hard limit — events exceeding this raise `ValidationError` before any network call. For `track_clinical_note` specifically, if the payload exceeds 512 KB the SDK raises `ValidationError` with a message indicating the note is too large; the caller is responsible for truncating or chunking. No silent truncation. |
| Documentation warnings | All public docs and docstrings clearly warn against sending direct patient identifiers.                                                                                                                                                                                                                                                  |

Customers are responsible for pseudonymisation upstream. A future validator version may detect additional PII patterns.

### 9.2 Server-side (Olira's infrastructure)

This is separate from SDK-side logging. Every event that reaches Olira's ingestion API is stored in full and is the basis for provenance and audit trails.

| Concern            | Behaviour                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full event storage | The complete event payload is stored server-side, including all clinical fields, timestamps, and metadata.                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Provenance         | Each event is stored as an `EventLog` document with a MongoDB `_id` assigned on insert. The SDK's `event_id` (UUID4) is the customer-facing identifier, persisted as `EventLog.event_id` by the ingestion endpoint — the stable bridge between what the customer sent and Olira's internal record. Events are queryable by `event_id`, `user_id` (resolved from `patient_id`), `type`, org (from API key), `timestamp`, and `ingested_at`. |
| State attribution  | Whenever an event changes Patient State, a `StateUpdateLog` document is created linking the `EventLog._id` to the exact state paths that changed (before/after values, module type). This is the internal mechanism behind Olira's event provenance — tracing Raw Event Log → State Module.                                                                                                                                                 |
| Audit trail        | The server-side record is the authoritative log of what data was submitted, by which organisation, and when.                                                                                                                                                                                                                                                                                                                                  |
| Deduplication      | `idempotency_key` prevents the server from storing duplicate events when the SDK retries a failed request (same event re-sent). **Note:** server-side deduplication on `idempotency_key` is not yet implemented — the field is sent but not currently used for deduplication.                                                                                                                                                               |

> Customers operating in regulated environments (HIPAA covered entities, etc.) should refer to Olira's data processing agreement for retention periods, access controls, and BAA terms. The SDK itself is the delivery mechanism — compliance obligations are governed at the platform level.

---

## 10. Packaging & Distribution

### Package Structure

```
packages/olira-sdk-python/
  src/olira/
    __init__.py          # public API: init, flush, log, log_batch, OliraClient, OliraLogType, exceptions
    client.py            # OliraClient class (sync); AsyncOliraClient class
    queue.py             # BackgroundWorker, bounded queue
    http.py              # HTTP transport, retry logic, send_batch_direct()
    models.py            # OliraLogType, OliraTrace, LogSpec, BatchResult, BatchError, Pydantic helpers
    exceptions.py        # Typed exception hierarchy
    py.typed             # PEP 561 marker
  tests/
    test_client.py
    test_async_client.py
    test_event_recorders.py
    test_retry.py
    test_privacy.py
  pyproject.toml         # uv project config + hatchling build backend
  uv.lock                # locked dependencies (mirrors monorepo convention)
  scripts/
    lint.sh              # ruff format + check + mypy
    test.sh              # pytest + coverage
    pre-pr.sh            # version + lint + test
  SPEC.md
  CHANGELOG.md
  LICENSE                # Apache 2.0
```

### Dependencies

| Dependency      | Purpose                                                              |
| --------------- | -------------------------------------------------------------------- |
| `pydantic>=2.0` | Public API schema models; validation at construction time            |
| `httpx>=0.27`   | Sync and async HTTP transport; connection pooling, timeouts, retries |

Schema models (e.g. `EsasItem`, `LabResultItem`, `PerformingLab`, `TimePeriod`) are exported from the top-level `olira` package. Field shapes align with `packages/common-models/.../schemas/personalization/util.py` (source of truth); the SDK does not depend on common-models so it remains public and PyPI-installable.

### Tooling (mirrors monorepo conventions)

| Tool        | Purpose                                                                                                                      |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `uv`        | Virtual environment, dependency management, build, publish — consistent with all other packages and services in the monorepo |
| `hatchling` | Build backend (declared in `pyproject.toml`, invoked via `uv build`)                                                         |
| `ruff`      | Formatting and linting                                                                                                       |
| `mypy`      | Type checking (`py.typed` PEP 561 marker)                                                                                    |
| `pytest`    | Tests with coverage reporting                                                                                                |
| Python      | 3.9+                                                                                                                         |

### Distribution

The SDK uses two registries — one private for internal development, one public for customers — following the same pattern as `utils` and `common-models`.

#### Registries

| Registry                                | Audience        | Install                                                  |
| --------------------------------------- | --------------- | -------------------------------------------------------- |
| AWS CodeArtifact (`raia-health` domain) | Olira engineers | `pip install olira --extra-index-url <codeartifact-url>` |
| PyPI (`olira`)                          | Customers       | `pip install olira`                                      |

#### CI Workflows

**On merge to `main`** (when `packages/olira-sdk-python/**/*.py` or `pyproject.toml` changes):

- Runs `.github/workflows/_publish-python-package.yml` in a 3-environment matrix.
- Publishes to all three CodeArtifact repositories in parallel:

| Environment | CodeArtifact Repository |
| ----------- | ----------------------- |
| `dev`       | `olira-private-dev`     |
| `stage`     | `olira-private-stage`   |
| `prod`      | `olira-private-prod`    |

- The workflow blocks pre-release versions (`alpha`, `beta`, `rc`) from reaching `prod` CodeArtifact — a safety check already enforced by `_publish-python-package.yml`.
- Uses OIDC (no stored secrets) — IAM role `arn:aws:iam::<account_id>:role/ci` per environment.

**On `v*` tag push** (e.g. `v1.0.0`):

- Publishes to public PyPI via Trusted Publishing (no `PYPI_TOKEN` stored in CI).
- Only stable versions are tagged — pre-release work stays in CodeArtifact.

#### Version Convention

| Version format                   | Publishes to        |
| -------------------------------- | ------------------- |
| `0.2.0a1`, `1.0.0b2`, `1.0.0rc1` | CodeArtifact only   |
| `1.0.0`, `1.1.0`, `2.0.0`        | CodeArtifact + PyPI |

SemVer throughout. Every release has a corresponding `CHANGELOG.md` entry.

#### Release Checklist

Before tagging a release, update in a single commit:

- `pyproject.toml` — bump `version`
- `src/olira/version.py` — bump `__version__`
- `uv.lock` — run `uv lock`
- `CHANGELOG.md` — add `## [x.y.z] - YYYY-MM-DD` entry

CI handles everything else after the tag is pushed.

#### `py.typed`

The `py.typed` PEP 561 marker is included so customers get full type checking with mypy or pyright against the installed package.

### License

Apache 2.0.

- Includes an explicit patent grant — both Olira and customers get patent protection as part of the licence terms.
- Standard for enterprise and healthcare SDKs; familiar to legal and procurement teams.
- Permissive enough that customers can embed the SDK in any commercial product without restriction.

---

## 11. Patient Management

The `api:manage-patients` scope grants full CRUD access to patients in your organisation. Patients must be created before events can be logged against them.

### Patient Model

```python
class ExternalIdentifier(BaseModel):
    system: str   # System name — e.g. "epic", "flatiron", "cerner", "fhir"
    value: str    # Patient ID in that system — MRN, FHIR resource ID, etc.

class Patient(BaseModel):
    id: str                                        # Olira-assigned — never changes
    first_name: str
    last_name: str
    sex: str
    timezone: str
    status: str                                    # "pending" | "active" | "deleted"
    email: str | None = None
    phone_number: str | None = None
    date_of_birth: str | None = None               # ISO 8601
    primary_disease_site: str | None = None
    disease_stage: str | None = None
    created_at: str | None = None                  # ISO 8601
    external_identifiers: list[ExternalIdentifier] = []
    metadata: dict[str, Any] | None = None
```

`id` is the Olira-assigned identifier returned by `create_patient()`. It is the MongoDB `_id` of the `PatientUser` document, serialised as a 24-character hex string. Use it in all subsequent calls that reference this patient.

`ExternalIdentifier` mirrors `ExternalIdentifier` in `packages/common-models/.../schemas/user/basic_user.py` — the SDK keeps its own copy so it remains PyPI-installable without depending on common-models.

### API Surface

```python
from olira import OliraClient, Patient, PatientListResult, ExternalIdentifier

client = OliraClient(api_key="olira_prod_...")

# Create — with external identifiers and metadata
patient: Patient = client.create_patient(
    first_name="Jane",
    last_name="Smith",
    timezone="America/New_York",
    primary_disease_site="breast",
    disease_stage="II",
    external_identifiers=[
        ExternalIdentifier(system="epic", value="MRN-00042"),
        ExternalIdentifier(system="flatiron", value="FLT-9981"),
    ],
    metadata={
        "site_code": "BOS-01",
        "trial_arm": "A",
        "enrolled_by_npi": "1234567890",
    },
)

# Get
patient = client.get_patient(patient_id=patient.id)

# List (paginated)
result: PatientListResult = client.list_patients(limit=50, offset=0)

# Look up by an external system's ID
result = client.list_patients(external_system="epic", external_value="MRN-00042")
patient = result.patients[0]

# Update (partial — omitted fields unchanged)
patient = client.update_patient(patient_id=patient.id, disease_stage="III")

# Add a metadata key (read → merge → write, metadata is full-replace on PUT)
current = client.get_patient(patient_id=patient.id)
client.update_patient(
    patient_id=patient.id,
    metadata={**(current.metadata or {}), "new_key": "value"},
)

# Soft-delete
client.delete_patient(patient_id=patient.id)
```

Module-level equivalents (`olira.create_patient(...)` etc.) proxy to the singleton client, matching the pattern of `olira.log()`.

### API Endpoints

| Method | Path | Action |
| ------ | ---- | ------ |
| `POST` | `/v1/patients` | Create patient |
| `GET` | `/v1/patients` | List patients (query params: `limit`, `offset`, `external_system`, `external_value`) |
| `GET` | `/v1/patients/{patient_id}` | Get patient by `id` |
| `PUT` | `/v1/patients/{patient_id}` | Update patient (partial) |
| `DELETE` | `/v1/patients/{patient_id}` | Soft-delete patient |

All five endpoints require the `api:manage-patients` scope on the API key and accept a raw API key (not a JWT) as the Bearer token.

`external_system` and `external_value` must be supplied together; supplying only one returns HTTP 422.

### ID Uniqueness

`id` must be unique within your organisation. Attempting to create a second patient with the same `id` returns HTTP 409 which the SDK surfaces as a `ValidationError`.

Soft-deleted patients still occupy their `id` — the identifier is not recycled after deletion. This is intentional: it preserves the audit trail linking events to that patient.

### `external_identifiers`

Stores the patient's identifiers in your external systems (EHR, HIE, FHIR server, oncology platform, etc.). One patient can carry IDs from multiple systems simultaneously.

| Constraint | Value |
| --- | --- |
| Type | `list[ExternalIdentifier]` |
| Max entries | 20 per patient |
| `system` | Printable ASCII, max 64 chars, lowercase recommended (e.g. `"epic"`, `"flatiron"`, `"cerner"`) |
| `value` | String, max 256 chars |
| Uniqueness | `(org_id, system, value)` must be unique. Attempting to assign an already-used pair to a second patient returns HTTP 409. |
| Indexed | Yes — compound multikey index on `(org_id, external_identifiers.system, external_identifiers.value)` |
| Update semantics | Full replace — the new list overwrites the previous one. |

### `metadata`

Stores arbitrary key-value pairs that are meaningful in your system but have no equivalent in Olira's core schema. Olira stores these verbatim and returns them on all reads, but never interprets or validates their values.

| Constraint | Value |
| --- | --- |
| Type | `dict` |
| Max keys | 50 |
| Key format | Printable ASCII, max 64 chars. Keys starting with `olira_` are reserved and will be rejected with HTTP 422. |
| Value types | `str` (max 512 chars), `int`, `float`, `bool`, `list` of scalars, `null`. No nested objects. |
| Total size | Serialised dict must be ≤ 8 KB. |
| Indexed | No — `metadata` is not filterable. Use `external_identifiers` for lookups. |
| Update semantics | Full replace — the new dict overwrites the previous one. Omitting `metadata` entirely on a `PUT` leaves the existing value unchanged. |

**What Olira does not do with `metadata`:** values are never read by ML models, clinical rules, the state-update engine, or any Console feature. They are opaque storage.

### Evolution policy — when does a `metadata` field get promoted to the core model?

A field living in `metadata` is a candidate for promotion when **all three** of the following are true:

1. At least three distinct customers are storing the same semantic concept (even under different key names).
2. Olira's platform needs to act on that data — ML, clinical rules, Console display, or reporting.
3. The concept has a clear, cross-customer definition that Olira can validate.

Promotion is a deliberate product decision. When a field is promoted, the API will continue accepting the old `metadata` key for one deprecation cycle, mirroring its value into the new first-class field server-side.

---

## 12. Patient Token

The `sdk:patient-token` scope allows a customer backend to mint short-lived JWTs locked to a single patient. The typical use case: a provider-facing backend needs to give a patient device access to the Olira MCP Patient State server without embedding a tenant-wide API key on the device.

### Flow

```
Customer Backend                    Olira API                    Patient Device
      │                                  │                               │
      │  POST /v1/auth/token             │                               │
      │  Bearer: olira_prod_...          │                               │
      │  { patient_id: "<patient id>" } ►│                               │
      │                                  │ lookup PatientUser by _id     │
      │                                  │ mint RS256 JWT                │
      │◄── { access_token, expires_in } ─│                               │
      │                                  │                               │
      │  forward JWT ────────────────────┼──────────────────────────────►│
      │                                  │                               │
      │                                  │◄── MCP tool call (JWT Bearer) ─│
      │                                  │ enforce patient_id from JWT   │
      │                                  │ (ignores tool argument)       │
```

The JWT is RS256-signed, valid for 15 minutes, and carries `user_type: "patient"` with `mcp:patient-state` scope. The MCP server enforces the locked `patient_id` regardless of what the caller passes in tool arguments — a patient's token cannot read another patient's data.

### API Surface

```python
from olira import OliraClient, PatientToken

client = OliraClient(api_key="olira_prod_...")  # must have sdk:patient-token scope

token: PatientToken = client.get_patient_token(patient_id="mrn-00042")
# token.access_token  — pass this to the patient device
# token.expires_in    — 900 (15 minutes)
# token.scopes        — ["mcp:patient-state"]
```

### Endpoint

| Method | Path | Scope required |
| ------ | ---- | -------------- |
| `POST` | `/v1/auth/token` | `sdk:patient-token` |

Request body: `{ "patient_id": "<your patient id>" }`

`patient_id` is the Olira-assigned patient id (the `id` returned by `POST /v1/patients`). The server looks up the `PatientUser` by `_id`, scoped to the calling organisation, and embeds the same ObjectId in the JWT's `patient_id` claim for the MCP to use directly.

---

## 13. Future Features

### OpenTelemetry Integration

Each `log()` call could create a short-lived OTel span (`olira.log {log_type}`) as a child of whatever span is active in the caller's code. Outbound HTTP requests would carry W3C `traceparent` / `tracestate` headers, allowing Olira's API to appear in the customer's existing distributed trace (Datadog, Honeycomb, Jaeger, etc.).

**Proposed design:**

- `opentelemetry-api>=1.20` as an optional dependency (`pip install olira[otel]`).
- A new `src/olira/otel.py` module with `log_span()` context manager and `get_traceparent_headers()` helper.
- All OTel behaviour would be a silent no-op when `opentelemetry-api` is not installed — no import errors, no runtime changes.
- `init()` would accept an optional `otel_tracer_provider` parameter; if omitted, the global OTel provider is used if present.

This feature adds observability value for customers already running OTel infrastructure but has no impact on customers who are not. Deferred to a future minor release.

---

## Appendix: Full Event Catalogue

Complete list of all log types with their `log_type` strings, categories, payload shapes, and field-level notes.

**Source of truth:** Event types are defined in the `EventLogTypeDefinition` catalog, seeded from:

- `services/app-api/data/event_log_type_definitions.jsonl` — 48 event type definitions (category, subtype, payload schema, target modules)
- `packages/common-models/src/olira_common_models/foundation/base/event_log_type_definition.py` — Pydantic model for catalog entries

Events generated internally by the platform (e.g. from the mobile app or internal pipelines) are defined in those sources but intentionally excluded from this SDK catalogue — the SDK only exposes events that external customer applications are expected to produce. Profile events are included here because they are required to populate `StableData`, a core section of the Patient State initialised at user creation time.

Fields marked `†` are computed server-side and must never be sent by clients.

---

### A.1 Symptom Reports (`symptom_reports`)

#### `symptom_report`

Unified symptom report. The `instrument` field determines the shape of the `symptoms` list — use `esas_r` for ESAS-r, `ctcae` or `pro_ctcae` for CTCAE graded reports, or any custom string for other instruments.

**Common fields:**

| Field                | Type    | Required | Notes                                                             |
| -------------------- | ------- | -------- | ----------------------------------------------------------------- |
| `instrument`         | `str`   | Yes      | `'esas_r'\|'ctcae'\|'pro_ctcae'\|'custom'\|<any>`                |
| `symptoms`           | `list`  | Yes      | Shape depends on instrument (see below)                           |
| `recall_period`      | `str`   | No       | `'now'\|'past_24h'`                                               |
| `recall_period_days` | `int`   | No       | Alternative numeric form                                          |

**`instrument=esas_r` — symptoms items (`EsasItem`):**

| Field                       | Type  | Required  | Notes                                                                                                     |
| --------------------------- | ----- | --------- | --------------------------------------------------------------------------------------------------------- |
| `symptoms[].name`           | `str` | Yes       | pain, tiredness, nausea, depression, anxiety, drowsiness, appetite, wellbeing, shortness_of_breath, other |
| `symptoms[].score`          | `int` | Yes       | 0–10                                                                                                      |
| `symptoms[].type`           | `str` | No        | Symptom type for matching when snomed_code/meddra_code unset                                              |
| `symptoms[].snomed_code`    | `str` | No        | SNOMED CT; first choice for matching                                                                      |
| `symptoms[].meddra_code`    | `str` | No        | MedDRA; used when snomed_code unset                                                                       |
| `subscale_scores.physical`  | `int` | †Computed | Server-side                                                                                               |
| `subscale_scores.emotional` | `int` | †Computed | Server-side                                                                                               |
| `subscale_scores.wellbeing` | `int` | †Computed | Server-side                                                                                               |

**`instrument=ctcae` or `pro_ctcae` — symptoms items:**

| Field                     | Type  | Required | Notes                                      |
| ------------------------- | ----- | -------- | ------------------------------------------ |
| `symptoms[].type`         | `str` | Yes      | Symptom name                               |
| `symptoms[].grade`        | `int` | Yes      | 0–5 (ctcae); 0–4 per dimension (pro_ctcae) |
| `symptoms[].frequency`    | `int` | No       | PRO-CTCAE only (0–4)                       |
| `symptoms[].interference` | `int` | No       | PRO-CTCAE only (0–4)                       |
| `symptoms[].onset`        | `str` | No       | ISO 8601 datetime                          |
| `symptoms[].snomed_code`  | `str` | No       | SNOMED CT preferred                        |
| `symptoms[].meddra_code`  | `str` | No       | MedDRA secondary                           |

**`instrument=custom` — symptoms items:**

| Field                    | Type    | Required | Notes  |
| ------------------------ | ------- | -------- | ------ |
| `symptoms[].type`        | `str`   | Yes      | Symptom type key |
| `symptoms[].name`        | `str`   | Yes      | Display name     |
| `symptoms[].score`       | `float` | Yes      | —      |
| `symptoms[].scale_min`   | `float` | No       | —      |
| `symptoms[].scale_max`   | `float` | No       | —      |
| `symptoms[].snomed_code` | `str`   | No       | —      |
| `symptoms[].meddra_code` | `str`   | No       | —      |

---

#### `symptom_free_text`

Unstructured natural language symptom description.

| Field                 | Type        | Required | Notes                             |
| --------------------- | ----------- | -------- | --------------------------------- |
| `text`                | `str`       | Yes      | Free-text description             |
| `associated_symptoms` | `list[str]` | No       | Structured symptom names if known |

---

#### `symptom_detail`

Follow-up detail on a previously reported symptom.

| Field          | Type  | Required | Notes                                                                           |
| -------------- | ----- | -------- | ------------------------------------------------------------------------------- |
| `type`         | `str` | Yes      | Symptom name/key                                                                |
| `detail_type`  | `str` | Yes      | `'location'\|'duration'\|'character'\|'trigger'\|'alleviating_factor'\|'other'` |
| `response`     | `str` | Yes      | Patient's response                                                              |
| `question`     | `str` | No       | Question text that prompted the detail                                          |
| `snomed_code`  | `str` | No       | —                                                                               |
| `meddra_code`  | `str` | No       | —                                                                               |

---

#### `functional_class_reported`

NYHA functional class or CCS angina class.

| Field                                         | Type                     | Required | Notes         |
| --------------------------------------------- | ------------------------ | -------- | ------------- |
| `instrument`                                  | `'nyha'\|'ccs'`          | Yes      | —             |
| `functional_class`                            | `int`                    | Yes      | 1–4           |
| `reported_by`                                 | `'patient'\|'clinician'` | No       | —             |
| `change_from_prior.previous_functional_class` | `int`                    | No       | —             |
| `change_from_prior.date`                      | `str`                    | No       | ISO 8601 date |

---

#### `health_metric_reported`

Scalar patient-reported health metric (not a formal symptom or validated instrument).

| Field         | Type    | Required | Notes                                                                  |
| ------------- | ------- | -------- | ---------------------------------------------------------------------- |
| `metric_type` | `str`   | Yes      | `'wellbeing'\|'energy'\|'pain_nrs'\|'appetite'\|'hydration'\|<custom>` |
| `score`       | `float` | Yes      | —                                                                      |
| `scale_min`   | `float` | Yes      | —                                                                      |
| `scale_max`   | `float` | Yes      | —                                                                      |
| `source`      | `str`   | No       | `'checkin'\|'spontaneous'\|'prompted'`                                 |

---

#### `moods_report`

User-reported mood states with optional intensity.

| Field               | Type             | Required | Notes             |
| ------------------- | ---------------- | -------- | ----------------- |
| `moods`             | `list[MoodItem]` | Yes      | At least one item |
| `moods[].mood`      | `str`            | Yes      | Mood label        |
| `moods[].intensity` | `int`            | No       | 0–10              |
| `source`            | `str`            | No       | Source context    |

---

### A.2 Lab & Clinical (`lab_clinical`)

#### `lab_results_received`

One or more lab results, optionally grouped into a named panel.

**Envelope fields:**

| Field                        | Type                  | Required | Notes                      |
| ---------------------------- | --------------------- | -------- | -------------------------- |
| `results`                    | `list[LabResultItem]` | Yes      | At least one item          |
| `panel_loinc_code`           | `str`                 | No       | LOINC code for named panel |
| `panel_name`                 | `str`                 | No       | Human-readable panel name  |
| `collection_datetime`        | `str`                 | No       | ISO 8601 datetime          |
| `source`                     | `str`                 | No       | e.g. 'redox', 'manual'     |
| `ordered_by_npi`             | `str`                 | No       | —                          |
| `ordering_provider_name`     | `str`                 | No       | —                          |
| `performing_lab.name`        | `str`                 | No       | —                          |
| `performing_lab.clia_number` | `str`                 | No       | —                          |
| `performing_lab.npi`         | `str`                 | No       | —                          |

**Per-result fields (with LOINC — preferred):**

| Field                  | Type    | Required              | Notes                                 |
| ---------------------- | ------- | --------------------- | ------------------------------------- |
| `loinc_code`           | `str`   | Yes (if no test_name) | —                                     |
| `value_numeric`        | `float` | Cond.                 | One of value_numeric or value_string  |
| `value_string`         | `str`   | Cond.                 | —                                     |
| `unit`                 | `str`   | Yes                   | —                                     |
| `abnormal_flag`        | `str`   | No                    | `'H'\|'L'\|'N'\|'HH'\|'LL'`           |
| `reference_range_low`  | `float` | No                    | —                                     |
| `reference_range_high` | `float` | No                    | —                                     |
| `result_status`        | `str`   | No                    | `'final'\|'preliminary'\|'corrected'` |
| `test_name` †          | `str`   | †Computed             | Resolved from LOINC server-side       |
| `specimen_type` †      | `str`   | †Computed             | Resolved from LOINC server-side       |

**Per-result fields (without LOINC — fallback):**

| Field                        | Type  | Required               | Notes                                                                                                       |
| ---------------------------- | ----- | ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| `test_name`                  | `str` | Yes (if no loinc_code) | —                                                                                                           |
| `specimen_type`              | `str` | No                     | —                                                                                                           |
| `test_category`              | `str` | No                     | `'hematology'\|'metabolic'\|'lipid'\|'oncology_marker'\|'cardiac'\|'diabetes'\|'renal'\|'hepatic'\|'other'` |
| (other fields same as above) |       |                        |                                                                                                             |

---

#### `vitals_measurement`

Structured vital signs reading from any source.

| Field                               | Type                 | Required | Notes                                                 |
| ----------------------------------- | -------------------- | -------- | ----------------------------------------------------- |
| `measurements`                      | `VitalsMeasurements` | Yes      | At least one measurement key                          |
| `measurements.systolic_bp_mmhg`     | `float`              | No       | —                                                     |
| `measurements.diastolic_bp_mmhg`    | `float`              | No       | —                                                     |
| `measurements.heart_rate_bpm`       | `float`              | No       | —                                                     |
| `measurements.spo2_percent`         | `float`              | No       | —                                                     |
| `measurements.weight_kg`            | `float`              | No       | —                                                     |
| `measurements.temperature_celsius`  | `float`              | No       | —                                                     |
| `measurements.respiratory_rate_bpm` | `float`              | No       | —                                                     |
| `source`                            | `str`                | Yes      | `'connected_device'\|'manual_entry'\|'ehr_flowsheet'` |
| `context.position`                  | `str`                | No       | `'sitting'\|'standing'\|'supine'`                     |
| `context.fasting`                   | `bool`               | No       | —                                                     |
| `collection_datetime`               | `str`                | No       | ISO 8601 datetime                                     |

---

#### `clinical_note_received`

Clinical note or history section from EHR/HIE or manual entry.

| Field              | Type         | Required | Notes                                                  |
| ------------------ | ------------ | -------- | ------------------------------------------------------ |
| `note_type`        | `str`        | Yes      | See values below                                       |
| `source`           | `str`        | Yes      | `'manual_entry'\|'ehr_integration'\|'hie_integration'` |
| `text`             | `str`        | Cond.    | One of text or sections                                |
| `sections`         | `list[dict]` | Cond.    | `[{section_label, content}]`                           |
| `loinc_code`       | `str`        | No       | LOINC for note type                                    |
| `authored_by.name` | `str`        | No       | —                                                      |
| `authored_by.npi`  | `str`        | No       | —                                                      |
| `authored_by.role` | `str`        | No       | —                                                      |
| `authored_date`    | `str`        | No       | ISO 8601 date                                          |
| `encounter_id`     | `str`        | No       | —                                                      |

`note_type` values: `progress_note`, `history_and_physical`, `social_history`, `family_history`, `medical_history`, `surgical_history`, `psychosocial_history`, `financial_history`, `discharge_summary`, `consultation_note`, `other`.

---

### A.3 Questionnaires (`questionnaires`)

#### `questionnaire_response`

Complete multi-item questionnaire response (validated or custom).

| Field                                    | Type                      | Required  | Notes                                      |
| ---------------------------------------- | ------------------------- | --------- | ------------------------------------------ |
| `instrument_id`                          | `str`                     | Yes       | e.g. `'phq9'`, `'kccq12'`, `'my_custom_q'` |
| `instrument_type`                        | `'validated'\|'custom'`   | Yes       | —                                          |
| `instrument_version`                     | `str`                     | No        | —                                          |
| `recall_period_days`                     | `int`                     | No        | —                                          |
| `items`                                  | `list[QuestionnaireItem]` | Yes       | —                                          |
| `items[].item_number`                    | `int`                     | Yes       | —                                          |
| `items[].response_value`                 | `float\|str`              | Yes       | —                                          |
| `items[].item_text`                      | `str`                     | Cond.     | Required for custom instruments            |
| `items[].response_label`                 | `str`                     | No        | —                                          |
| `items[].response_scale_max`             | `float`                   | No        | —                                          |
| `scores.total_score`                     | `float`                   | Yes       | —                                          |
| `scores.total_score_max`                 | `float`                   | No        | —                                          |
| `scores.severity_category`               | `str`                     | No        | —                                          |
| `scores.domain_scores`                   | `dict[str, float]`        | No        | —                                          |
| `scores.clinically_significant`          | `bool`                    | No        | —                                          |
| `administration.administration_mode`     | `str`                     | No        | —                                          |
| `administration.platform`                | `str`                     | No        | —                                          |
| `administration.language`                | `str`                     | No        | —                                          |
| `administration.completion_time_seconds` | `int`                     | No        | —                                          |
| `scoring_method` †                       |                           | †Computed | Server-side for validated instruments      |
| `change_vs_prior` †                      |                           | †Computed | Server-side for validated instruments      |

---

#### `questionnaire_item_response`

Single standalone question-answer pair (not part of a complete instrument submission).

| Field                | Type         | Required | Notes                                      |
| -------------------- | ------------ | -------- | ------------------------------------------ |
| `question`           | `str`        | Yes      | Question text                              |
| `response_value`     | `float\|str` | Yes      | —                                          |
| `response_scale_max` | `float`      | No       | —                                          |
| `response_label`     | `str`        | No       | —                                          |
| `instrument_id`      | `str`        | No       | If part of a known instrument              |
| `item_number`        | `int`        | No       | —                                          |
| `context`            | `str`        | No       | `'conversation'\|'check_in'\|'standalone'` |

---

### A.4 Conversations (`conversations`)

#### `conversation_completed`

Emitted when a chat or voice conversation ends. Triggers memory creation.

| Field              | Type                          | Required | Notes                                                           |
| ------------------ | ----------------------------- | -------- | --------------------------------------------------------------- |
| `conversation_id`  | `str`                         | No       | Correlates with conversation turns                              |
| `channel`          | `str`                         | No       | `'chat'\|'voice'\|'video'\|'sms'`                               |
| `duration_seconds` | `int`                         | No       | —                                                               |
| `language`         | `str`                         | No       | BCP 47 language tag                                             |
| `participants`     | `list[dict]`                  | No       | `[{role: 'patient'\|'agent'\|'clinician'\|'care_coordinator'}]` |
| `transcript`       | `str\|list[ConversationTurn]` | No       | Full text or structured turns                                   |

---

#### `conversation_turn_logged`

Single turn within an ongoing conversation. For incremental logging pattern.

| Field             | Type  | Required | Notes                                                 |
| ----------------- | ----- | -------- | ----------------------------------------------------- |
| `conversation_id` | `str` | Yes      | Must match `conversation_completed.conversation_id`   |
| `turn_index`      | `int` | Yes      | 0-based                                               |
| `speaker_label`   | `str` | Yes      | `'patient'\|'agent'\|'clinician'\|'care_coordinator'` |
| `text`            | `str` | Yes      | —                                                     |
| `channel`         | `str` | No       | —                                                     |

---

### A.5 Passive Data (`passive_data`)

#### `heart_rate_data_received`

Aggregated heart rate or HRV data from a device or integration.

| Field                    | Type    | Required | Notes                                    |
| ------------------------ | ------- | -------- | ---------------------------------------- |
| `period.start_datetime`  | `str`   | Yes      | ISO 8601                                 |
| `period.end_datetime`    | `str`   | Yes      | ISO 8601                                 |
| `device_provider`        | `str`   | Yes      | e.g. `'withings'`, `'garmin'`, `'terra'` |
| `resting_bpm`            | `float` | No       | At least one measurement recommended     |
| `avg_bpm`                | `float` | No       | —                                        |
| `min_bpm`                | `float` | No       | —                                        |
| `max_bpm`                | `float` | No       | —                                        |
| `avg_hrv_sdnn_ms`        | `float` | No       | —                                        |
| `irregular_events_count` | `int`   | No       | —                                        |

---

#### `sleep_data_received`

Sleep session data.

| Field                   | Type  | Required | Notes                                |
| ----------------------- | ----- | -------- | ------------------------------------ |
| `period.start_datetime` | `str` | Yes      | ISO 8601                             |
| `period.end_datetime`   | `str` | Yes      | ISO 8601                             |
| `device_provider`       | `str` | Yes      | —                                    |
| `total_sleep_minutes`   | `int` | No       | At least one measurement recommended |
| `deep_sleep_minutes`    | `int` | No       | —                                    |
| `rem_sleep_minutes`     | `int` | No       | —                                    |
| `light_sleep_minutes`   | `int` | No       | —                                    |
| `awake_minutes`         | `int` | No       | —                                    |

---

#### `activity_data_received`

Daily activity summary from wearable or Terra API.

| Field                     | Type    | Required | Notes    |
| ------------------------- | ------- | -------- | -------- |
| `period.start_datetime`   | `str`   | Yes      | ISO 8601 |
| `period.end_datetime`     | `str`   | Yes      | ISO 8601 |
| `device_provider`         | `str`   | Yes      | —        |
| `steps`                   | `int`   | No       | —        |
| `walking_minutes`         | `int`   | No       | —        |
| `active_minutes`          | `int`   | No       | —        |
| `sedentary_minutes`       | `int`   | No       | —        |
| `calories_total`          | `float` | No       | kcal     |
| `calories_active`         | `float` | No       | kcal     |
| `floors_climbed`          | `int`   | No       | —        |
| `distance_travelled_feet` | `float` | No       | —        |
| `walks`                   | `int`   | No       | —        |
| `time_at_home_percent`    | `float` | No       | —        |
| `exercise_sessions`       | `list`  | No       | —        |

---

#### `cgm_reading_received`

Continuous glucose monitor reading (Dexcom, Freestyle Libre via Terra).

| Field              | Type    | Required | Notes                     |
| ------------------ | ------- | -------- | ------------------------- |
| `glucose_mg_dl`    | `float` | Yes      | —                         |
| `sensor_timestamp` | `str`   | Yes      | ISO 8601                  |
| `device_provider`  | `str`   | Yes      | —                         |
| `trend_arrow`      | `str`   | No       | Arrow direction code      |
| `glucose_flag`     | `str`   | No       | `'high'\|'low'\|'normal'` |

---

#### `spo2_reading_received`

Pulse oximeter or wearable SpO2 reading.

| Field                 | Type    | Required | Notes                                   |
| --------------------- | ------- | -------- | --------------------------------------- |
| `spo2_percent`        | `float` | Yes      | —                                       |
| `sensor_timestamp`    | `str`   | Yes      | ISO 8601                                |
| `device_provider`     | `str`   | Yes      | —                                       |
| `pulse_bpm`           | `float` | No       | —                                       |
| `measurement_context` | `str`   | No       | `'resting'\|'during_sleep'\|'activity'` |

---

#### `weight_measurement_received`

Weight scale reading. Critical for heart failure decompensation detection (>2 kg gain in 24–48 h triggers alert server-side).

| Field              | Type    | Required | Notes    |
| ------------------ | ------- | -------- | -------- |
| `weight_kg`        | `float` | Yes      | —        |
| `sensor_timestamp` | `str`   | Yes      | ISO 8601 |
| `device_provider`  | `str`   | Yes      | —        |
| `body_fat_percent` | `float` | No       | —        |
| `bmi`              | `float` | No       | —        |

---

### A.6 Medication (`medication`)

#### `medication_action`

Unified medication list change. Use `action` to distinguish whether medications are being added, updated (patch), or deleted.

| Field                                    | Type                   | Required  | Notes                                                            |
| ---------------------------------------- | ---------------------- | --------- | ---------------------------------------------------------------- |
| `action`                                 | `str`                  | Yes       | `'add'\|'update'\|'delete'`                                      |
| `medications`                            | `list[dict]`           | Yes       | Shape varies by action (see below)                               |
| `medications[].rxnorm_cui`               | `str`                  | Cond.     | Preferred; one of rxnorm_cui or medication_name                  |
| `medications[].medication_name`          | `str`                  | Cond.     | Fallback                                                         |
| `medications[].dose`                     | `float`                | No        | For `add`/`update`                                               |
| `medications[].dose_unit`                | `str`                  | No        | —                                                                |
| `medications[].frequency`                | `str`                  | No        | —                                                                |
| `medications[].route`                    | `str`                  | No        | —                                                                |
| `medications[].form`                     | `str`                  | No        | —                                                                |
| `medications[].start_date`               | `str`                  | No        | ISO 8601 date                                                    |
| `medications[].schedule_times`           | `list[str]`            | No        | HH:MM strings; triggers adherence tracking                       |
| `medications[].adherence_window_minutes` | `int`                  | No        | Default 60                                                       |
| `medications[].prescribed_by.npi`        | `str`                  | No        | —                                                                |
| `therapeutic_class` †                    | `str`                  | †Computed | Resolved from RxNorm server-side                                 |

For `action=update`: include identifier + only changed fields. For `action=delete`: include only `rxnorm_cui` or `medication_name` per item.

---

#### `medication_dose_update`

One or more dose outcomes (taken or skipped).

| Field                                    | Type                 | Required  | Notes                                       |
| ---------------------------------------- | -------------------- | --------- | ------------------------------------------- |
| `medication_adherence`                   | `list[DoseRecord]`   | Yes       | —                                           |
| `medication_adherence[].status`          | `'taken'\|'skipped'` | Yes       | —                                           |
| `medication_adherence[].rxnorm_cui`      | `str`                | Cond.     | One of rxnorm_cui or medication_name        |
| `medication_adherence[].medication_name` | `str`                | Cond.     | —                                           |
| `medication_adherence[].scheduled_time`  | `str`                | No        | ISO 8601 datetime                           |
| `medication_adherence[].dose_amount`     | `float`              | No        | —                                           |
| `medication_adherence[].dose_unit`       | `str`                | No        | —                                           |
| `source`                                 | `str`                | No        | `'patient_app'\|'smart_pill_bottle'\|'ehr'` |
| `consecutive_miss_count` †               |                      | †Computed | Server-side                                 |
| `pdc` †                                  |                      | †Computed | Proportion of Days Covered; server-side     |

---

#### `medication_adverse_event_reported`

Patient-reported adverse drug reaction or side effect.

| Field                   | Type    | Required | Notes                                        |
| ----------------------- | ------- | -------- | -------------------------------------------- |
| `rxnorm_cui`            | `str`   | Cond.    | One of rxnorm_cui or medication_name         |
| `medication_name`       | `str`   | Cond.    | Fallback                                     |
| `adverse_event`         | `str`   | Yes      | Description of the adverse event             |
| `severity`              | `str`   | No       | `'mild'\|'moderate'\|'severe'\|'life_threatening'` |
| `onset_date`            | `str`   | No       | ISO 8601 date                                |
| `resolved`              | `bool`  | No       | Whether the event has resolved               |

---

### A.7 Engagement (`engagement`)

#### `user_login`

User authenticated and entered the application.

| Field                        | Type | Required | Notes                      |
| ---------------------------- | ---- | -------- | -------------------------- |
| (no required payload fields) |      |          | Optional metadata accepted |

---

#### `user_logout`

User session ended.

| Field                        | Type | Required | Notes                      |
| ---------------------------- | ---- | -------- | -------------------------- |
| (no required payload fields) |      |          | Optional metadata accepted |

---

#### `content_interacted`

User performed an action on a content item. Replaces `card_viewed`, `card_bookmarked`, `card_dismissed`.

| Field                | Type  | Required | Notes                                                                   |
| -------------------- | ----- | -------- | ----------------------------------------------------------------------- |
| `content_type`       | `str` | Yes      | Open string — client-defined vocabulary                                 |
| `action`             | `str` | Yes      | `'viewed'\|'bookmarked'\|'dismissed'\|'completed'\|'shared'\|'clicked'` |
| `content_id`         | `str` | No       | —                                                                       |
| `title`              | `str` | No       | —                                                                       |
| `dwell_time_seconds` | `int` | No       | —                                                                       |
| `reason`             | `str` | No       | e.g. for dismissals                                                     |

---

#### `notification_interacted`

User interacted with a push notification. Replaces `notification_opened` and `notification_dismissed`.

| Field                  | Type  | Required | Notes                                   |
| ---------------------- | ----- | -------- | --------------------------------------- |
| `notification_type`    | `str` | Yes      | Open string — client-defined vocabulary |
| `action`               | `str` | Yes      | `'opened'\|'dismissed'\|'snoozed'`      |
| `delivered_at`         | `str` | No       | ISO 8601                                |
| `time_to_open_seconds` | `int` | No       | —                                       |

---

#### `task_updated`

User completed or skipped a discrete task or guided flow. Replaces `checkin_completed`, `questionnaire_skipped`.

| Field                     | Type  | Required | Notes                                   |
| ------------------------- | ----- | -------- | --------------------------------------- |
| `task_type`               | `str` | Yes      | Open string — client-defined vocabulary |
| `action`                  | `str` | Yes      | `'completed'\|'skipped'`                |
| `task_id`                 | `str` | No       | —                                       |
| `task_description`        | `str` | No       | —                                       |
| `completion_time_seconds` | `int` | No       | —                                       |

---

#### `interaction_feedback`

User gave explicit feedback on a system-generated item. Replaces `message_feedback`.

| Field           | Type  | Required | Notes                                            |
| --------------- | ----- | -------- | ------------------------------------------------ |
| `target_type`   | `str` | Yes      | `'message'\|'content'\|<custom>`                 |
| `feedback_type` | `str` | Yes      | Client-defined (e.g. `'thumbs_up'`, `'flagged'`) |
| `target_id`     | `str` | No       | —                                                |

---

#### `feature_used`

User interacted with a named application feature.

| Field                | Type  | Required | Notes                                   |
| -------------------- | ----- | -------- | --------------------------------------- |
| `feature_name`       | `str` | Yes      | Open string — client-defined vocabulary |
| `session_id`         | `str` | No       | —                                       |
| `dwell_time_seconds` | `int` | No       | —                                       |

---

### A.8 Profile (`profile`)

All profile events are patch-style — include only the `patient_id` and fields that changed.

#### `demographics_updated`

| Field             | Type  | Required | Notes         |
| ----------------- | ----- | -------- | ------------- |
| `name`            | `str` | No       | —             |
| `dob`             | `str` | No       | ISO 8601 date |
| `sex`             | `str` | No       | —             |
| `marital_status`  | `str` | No       | —             |
| `address.street`  | `str` | No       | —             |
| `address.city`    | `str` | No       | —             |
| `address.state`   | `str` | No       | —             |
| `address.zip`     | `str` | No       | —             |
| `address.country` | `str` | No       | —             |
| `phone`           | `str` | No       | —             |
| `email`           | `str` | No       | —             |
| `language`        | `str` | No       | BCP 47        |
| `ethnicity`       | `str` | No       | —             |

---

#### `condition_updated`

Clinical diagnosis information. Distinct from `treatment_phase_changed`.

| Field            | Type        | Required | Notes         |
| ---------------- | ----------- | -------- | ------------- |
| `disease_type`   | `str`       | No       | —             |
| `stage`          | `str`       | No       | —             |
| `diagnosis_date` | `str`       | No       | ISO 8601 date |
| `icd10_codes`    | `list[str]` | No       | —             |

---

#### `preferences_updated`

Patient communication and lifestyle preferences.

| Field                            | Type        | Required | Notes |
| -------------------------------- | ----------- | -------- | ----- |
| `reading_level`                  | `str`       | No       | —     |
| `tone`                           | `str`       | No       | —     |
| `dietary_preferences`            | `list[str]` | No       | —     |
| `comfort_with_technology`        | `str`       | No       | —     |
| `energy_level`                   | `str`       | No       | —     |
| `symptoms_need_help_managing`    | `list[str]` | No       | —     |
| `things_to_track`                | `list[str]` | No       | —     |
| `notification_preferences.push`  | `bool`      | No       | —     |
| `notification_preferences.email` | `bool`      | No       | —     |
| `notification_preferences.sms`   | `bool`      | No       | —     |

---

#### `emergency_contact_updated`

Healthcare proxy or emergency contact.

| Field          | Type  | Required | Notes |
| -------------- | ----- | -------- | ----- |
| `name`         | `str` | No       | —     |
| `relationship` | `str` | No       | —     |
| `phone`        | `str` | No       | —     |
| `email`        | `str` | No       | —     |

---

#### `care_team_updated`

Providers associated with patient care. Supports add, update, and remove in one submission.

| Field                    | Type                   | Required | Notes                             |
| ------------------------ | ---------------------- | -------- | --------------------------------- |
| `members`                | `list[CareTeamMember]` | Yes      | At least one member               |
| `members[].action`       | `str`                  | Yes      | `'add'\|'update'\|'remove'`       |
| `members[].role`         | `str`                  | Yes      | —                                 |
| `members[].npi`          | `str`                  | No       | Preferred identifier for matching |
| `members[].name`         | `str`                  | No       | —                                 |
| `members[].organization` | `str`                  | No       | —                                 |

---

#### `insurance_updated`

Payer and plan information.

| Field       | Type  | Required | Notes |
| ----------- | ----- | -------- | ----- |
| `payer`     | `str` | No       | —     |
| `plan_name` | `str` | No       | —     |
| `member_id` | `str` | No       | —     |
| `group_id`  | `str` | No       | —     |

---

#### `social_updated`

Social determinants of health.

| Field                   | Type  | Required | Notes |
| ----------------------- | ----- | -------- | ----- |
| `living_situation`      | `str` | No       | —     |
| `support_system`        | `str` | No       | —     |
| `transportation_access` | `str` | No       | —     |
| `employment_status`     | `str` | No       | —     |
| `housing_stability`     | `str` | No       | —     |

---

#### `pharmacy_updated`

Patient's local pharmacy.

| Field     | Type  | Required | Notes |
| --------- | ----- | -------- | ----- |
| `name`    | `str` | No       | —     |
| `address` | `str` | No       | —     |
| `phone`   | `str` | No       | —     |

---

#### `treatment_phase_changed`

Treatment phase transition. Triggers downstream alert threshold changes and care plan adjustments.

| Field            | Type  | Required | Notes                                                           |
| ---------------- | ----- | -------- | --------------------------------------------------------------- |
| `new_phase`      | `str` | Yes      | `'active_treatment'\|'surveillance'\|'palliative'\|'remission'` |
| `effective_date` | `str` | Yes      | ISO 8601 date                                                   |
| `changed_by`     | `str` | Yes      | `'clinician'\|'system'`                                         |
| `previous_phase` | `str` | No       | —                                                               |

---

### A.9 Event Category Summary

| Category        | `log_type` strings                                                                                                                                                                                       | Count  |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Symptom Reports | `symptom_ctcae_grade`, `symptom_esas_report`, `symptom_custom_report`, `symptom_free_text`, `symptom_detail`, `functional_class_reported`, `health_metric_reported`, `moods_report`                        | 8      |
| Lab & Clinical  | `lab_results_received`, `vitals_measurement`, `clinical_note_received`                                                                                                                                     | 3      |
| Questionnaires  | `questionnaire_response`, `questionnaire_item_response`                                                                                                                                                    | 2      |
| Conversations   | `conversation_completed`, `conversation_turn_logged`                                                                                                                                                       | 2      |
| Passive Data    | `heart_rate_data_received`, `sleep_data_received`, `activity_data_received`, `cgm_reading_received`, `spo2_reading_received`, `weight_measurement_received`                                                | 6      |
| Medication      | `medication_added`, `medication_updated`, `medication_deleted`, `medication_dose_update`                                                                                                                   | 4      |
| Engagement      | `user_login`, `user_logout`, `content_interacted`, `notification_interacted`, `task_updated`, `interaction_feedback`, `feature_used`                                                                       | 7      |
| Profile         | `demographics_updated`, `condition_updated`, `preferences_updated`, `emergency_contact_updated`, `care_team_updated`, `insurance_updated`, `social_updated`, `pharmacy_updated`, `treatment_phase_changed` | 9      |
| **Total**       |                                                                                                                                                                                                            | **41** |

The 41 log types map to the event recorders in Section 5. Several recorders (e.g. `track_dose_taken` / `track_dose_skipped`) compose into a single underlying event (`medication_dose_update`), and a handful produce compound events with multiple sub-payloads, bringing the total recorder count above the raw event count.
