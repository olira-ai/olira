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
5. [Event Recorders](#5-event-recorders)
6. [Ingestion API Endpoints](#6-ingestion-api-endpoints)
7. [Delivery & Reliability](#7-delivery--reliability)
8. [Error Handling](#8-error-handling)
9. [Privacy & Compliance Defaults](#9-privacy--compliance-defaults)
10. [Packaging & Distribution](#10-packaging--distribution)
11. [Appendix: Full Event Catalogue](#appendix-full-event-catalogue)

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
- Key lifecycle (create / list / revoke) is already implemented in `services/app-api/routes/mcp/api_keys.py`.
- Key format: `olira_{hex}` (prefix stored for display; hash stored server-side).

### SDK-side Behaviour

- Accept key via:
  1. `olira.init(api_key="olira_prod_...")` — explicit
  2. `OLIRA_API_KEY` environment variable — fallback
- Key is **never logged** (redacted as `olira_***` in all debug output).
- Included in every HTTP request as `Authorization: Bearer olira_{env}_{key}`.

### Environment

```python
from enum import StrEnum

class Environment(StrEnum):
    PRODUCTION  = "production"
    DEVELOPMENT = "development"
```

`Environment.PRODUCTION` is the default. Use `Environment.DEVELOPMENT` for local development, CI, and staging systems — Olira will route these events away from live Patient State.

---

## 3. Public API Surface

### Module-level (singleton)

```python
import olira

# Minimal — only the API key is required
olira.init(api_key="olira_prod_...")   # or set OLIRA_API_KEY env var

# All calls are typed — no raw event name strings
olira.track_symptom_esas(subject_id="p_123", symptoms=[...])
olira.track_lab_results(subject_id="p_456", results=[...])
olira.flush()
```

Optional `init` parameters:

| Parameter      | Default                       | Why you'd set it                                                                                                                                                                                        |
| -------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `environment`  | `Environment.PRODUCTION`      | Set to `Environment.DEVELOPMENT` when sending from non-production systems. Olira routes events server-side based on this value — no URL change required.                                                |
| `service_name` | `None`                        | Name of the calling service (e.g. `"emr-integration"`, `"care-api"`). Useful for attribution and debugging when multiple services in your stack write to Olira. Single-backend customers can omit this. |
| `base_url`     | `"https://api.prod.olira.ai"` | Override only if directed by Olira support (e.g. pointing at a sandbox). Most customers never set this.                                                                                                 |
| `async_flush`  | `True`                        | Set to `False` to disable the background thread and flush synchronously on every `track_*` call. Use in serverless / Lambda environments where a background thread cannot persist between invocations.  |

### Explicit class (multi-tenant / dependency injection)

`OliraClient` is the primary class for multi-tenant apps (different API keys per tenant) and for dependency injection in tests. The module-level `olira.*` functions proxy to a singleton `OliraClient` created by `init()`.

```python
from olira import OliraClient, Environment

# Minimal
client = OliraClient(api_key="olira_prod_...")

# With optional parameters
client = OliraClient(
    api_key="olira_prod_...",
    environment=Environment.DEVELOPMENT,  # isolate non-prod data from Patient State
    service_name="emr-service",  # tag which service is writing events
    batch_size=50,
    flush_interval=1.5,
    max_queue_size=10_000,
    timeout=5.0,
    max_retries=3,
    on_error="drop",
    async_flush=True,  # set False for serverless / Lambda
)

# Only event recorders — no track() on OliraClient
client.track_lab_results(subject_id="p_456", results=[...])
client.flush()
```

### Async Client

```python
from olira import AsyncOliraClient

async with AsyncOliraClient(api_key=...) as client:
    await client.track_symptom_esas(subject_id="p_789", symptoms=[...])
    await client.flush()
```

`AsyncOliraClient` provides the same event recorders as `OliraClient` with `async def` signatures. Included in v1.

---

## 4. Event Model

### Required Fields (every event)

| Field        | Type  | Notes                                           |
| ------------ | ----- | ----------------------------------------------- |
| `event_name` | `str` | snake_case event type (see Appendix)            |
| `subject_id` | `str` | Pseudonymous patient identifier — no direct PII |

### Optional Fields

| Field             | Type              | Default              | Notes                                  |
| ----------------- | ----------------- | -------------------- | -------------------------------------- |
| `timestamp`       | ISO 8601 `str`    | Server time          | Client-provided timestamp              |
| `properties`      | `dict[str, JSON]` | `{}`                 | Event payload                          |
| `idempotency_key` | `str`             | Auto-generated UUID4 | Override to deduplicate retried events |
| `event_id`        | `str`             | Auto-generated UUID4 | Client-generated event identifier      |

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

> **Note:** Wire format is internal — SDK consumers use event recorders only. This section is documented for server implementers.

```json
{
  "event_name": "symptom_esas_report",
  "subject_id": "p_123_pseudo",
  "timestamp": "2026-02-26T08:15:00Z",
  "event_id": "e1a2b3c4-...",
  "idempotency_key": "c6f8b1...",
  "properties": {
    "symptoms": [
      { "name": "pain", "score": 4 },
      { "name": "nausea", "score": 2 }
    ],
    "total_score": 6,
    "recall_period": "past_24h"
  },
  "context": {
    "environment": "production",
    "service": "customer-backend",
    "sdk_version": "0.1.0",
    "sdk_language": "python"
  }
}
```

### subject_id Validation

The SDK raises `olira.ValidationError` before any network call if `subject_id`:

- Is empty or whitespace.
- Matches a known PII pattern: email address (`@` domain), US phone (`\d{10}`), or US SSN (`\d{3}-\d{2}-\d{4}`).

Customers are responsible for pseudonymisation. The SDK documentation clearly warns against sending direct patient identifiers.

---

## 5. Event Recorders

The SDK ships pre-built event recorders for all event types, reducing the risk of malformed payloads. Each recorder:

- Validates required fields client-side.
- Raises `olira.ValidationError` before any network call on malformed input (missing required fields, out-of-range scores, empty `subject_id`).
- Serializes directly to the wire format.

All recorders share this signature pattern:

```python
def track_<event>(self, subject_id: str, *, <required fields>, <optional fields with defaults>) -> None
```

### 5.1 Symptom Reports

| Recorder                  | Required fields                                                                          | Optional fields                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `track_symptom_ctcae`     | `subject_id`, `symptoms: list[CtcaeSymptom]`                                             | `instrument: 'ctcae'\|'pro_ctcae'`, `recall_period_days: int`    |
| `track_symptom_esas`      | `subject_id`, `symptoms: list[EsasItem]`                                                 | `recall_period: 'now'\|'past_24h'` — `total_score` auto-computed |
| `track_symptom_custom`    | `subject_id`, `symptoms: list[CustomSymptomItem]`                                        | `instrument: str`                                                |
| `track_symptom_free_text` | `subject_id`, `text: str`                                                                | `associated_symptoms: list[str]`                                 |
| `track_symptom_detail`    | `subject_id`, `symptom_type: str`, `detail_type: str`, `response: str`                   | `question: str`, `snomed_code: str`, `meddra_code: str`          |
| `track_functional_class`  | `subject_id`, `instrument: 'nyha'\|'ccs'`, `functional_class: int` (1–4)                 | `reported_by: 'patient'\|'clinician'`, `change_from_prior: dict` |
| `track_health_metric`     | `subject_id`, `metric_type: str`, `score: float`, `scale_min: float`, `scale_max: float` | `source: 'checkin'\|'spontaneous'\|'prompted'`                   |
| `track_moods`             | `subject_id`, `moods: list[MoodItem]`                                                    | `source: str`                                                    |

**Schemas:**

```python
class CtcaeSymptom(TypedDict):
    type: str                     # symptom name
    grade: int                    # 0–5 (ctcae) or 0–4 (pro_ctcae per dimension)
    frequency: NotRequired[int]   # pro_ctcae only
    interference: NotRequired[int]
    onset: NotRequired[str]       # ISO 8601
    snomed_code: NotRequired[str]
    meddra_code: NotRequired[str]

class EsasItem(TypedDict):
    name: str    # pain, tiredness, nausea, depression, anxiety, drowsiness,
                 # appetite, wellbeing, shortness_of_breath, other
    score: int   # 0–10

class CustomSymptomItem(TypedDict):
    type: str
    name: str
    score: float
    scale_min: NotRequired[float]
    scale_max: NotRequired[float]
    snomed_code: NotRequired[str]
    meddra_code: NotRequired[str]

class MoodItem(TypedDict):
    mood: str
    intensity: NotRequired[int]   # 0–10
```

**Example:**

```python
client.track_symptom_esas(
    subject_id="p_abc123",
    symptoms=[
        {"name": "pain", "score": 4},
        {"name": "nausea", "score": 2},
        {"name": "anxiety", "score": 5},
    ],
    recall_period="past_24h",
)
```

### 5.2 Lab & Clinical

| Recorder              | Required fields                                                 | Optional fields                                                                                                                                                     |
| --------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `track_lab_results`   | `subject_id`, `results: list[LabResultItem]`                    | `panel_name: str`, `panel_loinc_code: str`, `collection_datetime: str`, `ordered_by_npi: str`, `ordering_provider_name: str`, `performing_lab: dict`, `source: str` |
| `track_vitals`        | `subject_id`, `measurements: VitalsMeasurements`, `source: str` | `context: dict`, `collection_datetime: str`                                                                                                                         |
| `track_clinical_note` | `subject_id`, `note_type: str`, `source: str`                   | `text: str`, `sections: list[dict]`, `loinc_code: str`, `authored_by: dict`, `authored_date: str`, `encounter_id: str`                                              |

**Schemas:**

```python
class LabResultItem(TypedDict):
    # With LOINC (preferred)
    loinc_code: NotRequired[str]
    # Without LOINC (fallback — at least one of loinc_code or test_name required)
    test_name: NotRequired[str]
    specimen_type: NotRequired[str]
    test_category: NotRequired[str]  # 'hematology'|'metabolic'|'lipid'|...
    # Common
    value_numeric: NotRequired[float]
    value_string: NotRequired[str]   # at least one of value_numeric/value_string required
    unit: str
    abnormal_flag: NotRequired[str]  # 'H'|'L'|'N'|'HH'|'LL'
    reference_range_low: NotRequired[float]
    reference_range_high: NotRequired[float]
    result_status: NotRequired[str]  # 'final'|'preliminary'|'corrected'

class VitalsMeasurements(TypedDict, total=False):
    systolic_bp_mmhg: float
    diastolic_bp_mmhg: float
    heart_rate_bpm: float
    spo2_percent: float
    weight_kg: float
    temperature_celsius: float
    respiratory_rate_bpm: float
    # At least one measurement required
```

**Example:**

```python
client.track_lab_results(
    subject_id="p_abc123",
    results=[
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
    panel_name="CBC",
    collection_datetime="2026-02-26T07:30:00Z",
)
```

### 5.3 Questionnaires

| Recorder                   | Required fields                                                                                                                               | Optional fields                                                                                                                            |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `track_questionnaire`      | `subject_id`, `instrument_id: str`, `instrument_type: 'validated'\|'custom'`, `items: list[QuestionnaireItem]`, `scores: QuestionnaireScores` | `instrument_version: str`, `recall_period_days: int`, `administration: QuestionnaireAdmin`                                                 |
| `track_questionnaire_item` | `subject_id`, `question: str`, `response_value`                                                                                               | `response_scale_max`, `response_label: str`, `instrument_id: str`, `item_number: int`, `context: 'conversation'\|'check_in'\|'standalone'` |

**Schemas:**

```python
class QuestionnaireItem(TypedDict):
    item_number: int
    response_value: float | str
    item_text: NotRequired[str]       # required for custom instruments
    response_label: NotRequired[str]
    response_scale_max: NotRequired[float]

class QuestionnaireScores(TypedDict):
    total_score: float
    total_score_max: NotRequired[float]
    severity_category: NotRequired[str]
    domain_scores: NotRequired[dict[str, float]]
    clinically_significant: NotRequired[bool]
    significance_threshold: NotRequired[float]

class QuestionnaireAdmin(TypedDict, total=False):
    administration_mode: str   # 'patient_self_report'|'clinician_administered'|'caregiver_proxy'
    platform: str              # 'mobile_app'|'web'|'paper_transcribed'
    language: str
    completion_time_seconds: int
    items_completed: int
    items_skipped: int
    administered_by: NotRequired[dict]  # { name?, npi?, role? }
```

**Example:**

```python
client.track_questionnaire(
    subject_id="p_abc123",
    instrument_id="PHQ-9",
    instrument_type="validated",
    items=[
        {"item_number": i + 1, "response_value": v}
        for i, v in enumerate([1, 0, 2, 1, 0, 1, 2, 1, 0])
    ],
    scores={"total_score": 8, "severity_category": "mild"},
    administration={"administration_mode": "patient_self_report", "platform": "mobile_app"},
)
```

### 5.4 Conversations

| Recorder                       | Required fields                                                                            | Optional fields                                                                                                                                           |
| ------------------------------ | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `track_conversation_completed` | `subject_id`                                                                               | `conversation_id: str`, `channel: str`, `duration_seconds: int`, `language: str`, `participants: list[dict]`, `transcript: str \| list[ConversationTurn]` |
| `track_conversation_turn`      | `subject_id`, `conversation_id: str`, `turn_index: int`, `speaker_label: str`, `text: str` | `channel: str`                                                                                                                                            |

**Note on transcript patterns:** Either (1) send full transcript in `track_conversation_completed`, or (2) send incremental turns via `track_conversation_turn` and call `track_conversation_completed` without a transcript. Do not mix patterns for the same conversation.

```python
class ConversationTurn(TypedDict):
    speaker_label: str   # 'patient'|'agent'|'clinician'|'care_coordinator'
    text: str
    timestamp: NotRequired[str]
    turn_index: NotRequired[int]
```

**Example:**

```python
client.track_conversation_completed(
    subject_id="p_abc123",
    conversation_id="conv_789",
    channel="in_app_chat",
    duration_seconds=142,
    transcript=[
        {"speaker_label": "agent", "text": "How are you feeling today?", "turn_index": 0},
        {"speaker_label": "patient", "text": "A bit tired, pain is around a 4.", "turn_index": 1},
    ],
)
```

### 5.5 Passive Data

| Recorder            | Required fields                                                                       | Optional fields                                                                                                                                                                                                       |
| ------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `track_heart_rate`  | `subject_id`, `period: TimePeriod`, `device_provider: str`                            | `resting_bpm`, `avg_bpm`, `min_bpm`, `max_bpm`, `avg_hrv_sdnn_ms`, `irregular_events_count`                                                                                                                           |
| `track_sleep`       | `subject_id`, `period: TimePeriod`, `device_provider: str`                            | `total_sleep_minutes`, `deep_sleep_minutes`, `rem_sleep_minutes`, `light_sleep_minutes`, `awake_minutes`                                                                                                              |
| `track_activity`    | `subject_id`, `period: TimePeriod`, `device_provider: str`                            | `steps`, `walking_minutes`, `active_minutes`, `sedentary_minutes`, `calories_total`, `calories_active`, `floors_climbed`, `distance_travelled_feet`, `walks`, `time_at_home_percent`, `exercise_sessions: list[dict]` |
| `track_cgm_reading` | `subject_id`, `glucose_mg_dl: float`, `sensor_timestamp: str`, `device_provider: str` | `trend_arrow: str`, `glucose_flag: 'high'\|'low'\|'normal'`                                                                                                                                                           |
| `track_spo2`        | `subject_id`, `spo2_percent: float`, `sensor_timestamp: str`, `device_provider: str`  | `pulse_bpm: float`, `measurement_context: 'resting'\|'during_sleep'\|'activity'`                                                                                                                                      |
| `track_weight`      | `subject_id`, `weight_kg: float`, `sensor_timestamp: str`, `device_provider: str`     | `body_fat_percent: float`, `bmi: float`                                                                                                                                                                               |

```python
class TimePeriod(TypedDict):
    start_datetime: str   # ISO 8601
    end_datetime: str     # ISO 8601
```

**Example:**

```python
client.track_sleep(
    subject_id="p_abc123",
    period={"start_datetime": "2026-02-25T22:10:00Z", "end_datetime": "2026-02-26T06:45:00Z"},
    device_provider="withings",
    total_sleep_minutes=395,
    deep_sleep_minutes=72,
    rem_sleep_minutes=88,
    awake_minutes=20,
)
```

### 5.6 Medication

| Recorder                   | Required fields                                         | Optional fields                                        |
| -------------------------- | ------------------------------------------------------- | ------------------------------------------------------ |
| `track_medication_added`   | `subject_id`, `medications: list[MedicationItem]`       | —                                                      |
| `track_medication_updated` | `subject_id`, `medications: list[MedicationPatch]`      | —                                                      |
| `track_medication_deleted` | `subject_id`, `medications: list[MedicationIdentifier]` | —                                                      |
| `track_dose_taken`         | `subject_id`, `rxnorm_cui_or_name: str`                 | `scheduled_time: str`, `dose_amount`, `dose_unit: str` |
| `track_dose_skipped`       | `subject_id`, `rxnorm_cui_or_name: str`                 | `scheduled_time: str`, `dose_amount`, `dose_unit: str` |

**Medication identity:** `rxnorm_cui` is the preferred identifier. When provided, `medication_name` and `therapeutic_class` are resolved server-side. At least one of `rxnorm_cui` or `medication_name` must be present.

**`rxnorm_cui_or_name` parameter:** The `track_dose_taken` / `track_dose_skipped` recorders accept a single `rxnorm_cui_or_name` string. The SDK detects whether the value is an RxNorm CUI (digits only) or a name string and maps it to `rxnorm_cui` or `medication_name` on the wire accordingly.

```python
class MedicationItem(TypedDict):
    rxnorm_cui: NotRequired[str]    # preferred
    medication_name: NotRequired[str]
    ndc_code: NotRequired[str]
    dose: NotRequired[float]
    dose_unit: NotRequired[str]
    frequency: NotRequired[str]
    route: NotRequired[str]         # 'oral'|'iv'|'subcutaneous'|'topical'|'inhaled'|'other'
    form: NotRequired[str]          # 'tablet'|'capsule'|'liquid'|'injection'|'patch'|'other'
    therapeutic_class: NotRequired[str]
    start_date: NotRequired[str]
    schedule_times: NotRequired[list[str]]
    adherence_window_minutes: NotRequired[int]
    prescribed_by: NotRequired[dict]

class MedicationPatch(TypedDict):
    rxnorm_cui: NotRequired[str]       # at least one of rxnorm_cui or medication_name required (identifier)
    medication_name: NotRequired[str]
    dose: NotRequired[float]
    dose_unit: NotRequired[str]
    frequency: NotRequired[str]
    route: NotRequired[str]
    form: NotRequired[str]
    start_date: NotRequired[str]
    schedule_times: NotRequired[list[str]]
    adherence_window_minutes: NotRequired[int]

class MedicationIdentifier(TypedDict):
    rxnorm_cui: NotRequired[str]
    medication_name: NotRequired[str]
    # At least one required
```

**Example:**

```python
client.track_medication_added(
    subject_id="p_abc123",
    medications=[
        {
            "rxnorm_cui": "1049502",
            "medication_name": "Ondansetron 4mg",
            "dose": 4.0,
            "dose_unit": "mg",
            "frequency": "every_8h_as_needed",
            "route": "oral",
            "form": "tablet",
            "start_date": "2026-02-26",
        }
    ],
)
```

### 5.7 Engagement

| Recorder                         | Required fields                                                                    | Optional fields                                                                           |
| -------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `track_login`                    | `subject_id`                                                                       | —                                                                                         |
| `track_logout`                   | `subject_id`                                                                       | —                                                                                         |
| `track_content_interaction`      | `subject_id`, `content_type: str`, `action: str`                                   | `content_id: str`, `title: str`, `preview: str`, `dwell_time_seconds: int`, `reason: str` |
| `track_notification_interaction` | `subject_id`, `notification_type: str`, `action: 'opened'\|'dismissed'\|'snoozed'` | `delivered_at: str`, `time_to_open_seconds: int`                                          |
| `track_task_updated`             | `subject_id`, `task_type: str`, `action: 'completed'\|'skipped'`                   | `task_id: str`, `task_description: str`, `completion_time_seconds: int`                   |
| `track_interaction_feedback`     | `subject_id`, `target_type: str`, `feedback_type: str`                             | `target_id: str`                                                                          |
| `track_feature_used`             | `subject_id`, `feature_name: str`                                                  | `session_id: str`, `dwell_time_seconds: int`                                              |

**Generalisation principle:** `content_type`, `notification_type`, `task_type`, and `feature_name` are open strings. Customers define their own vocabulary.

**Example:**

```python
client.track_feature_used(
    subject_id="p_abc123",
    feature_name="symptom_tracker",
    session_id="sess_001",
    dwell_time_seconds=45,
)
```

### 5.8 Profile & Stable Data

All profile events are patch-style: include only the fields that changed. Omitted fields are left untouched server-side.

| Recorder                          | Required fields                                                                            | Optional/patch fields                                                                                                                                                   |
| --------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `track_demographics_updated`      | `subject_id`                                                                               | `name`, `dob`, `sex`, `marital_status`, `address`, `phone`, `email`, `language`, `ethnicity`                                                                            |
| `track_condition_updated`         | `subject_id`                                                                               | `disease_type`, `stage`, `diagnosis_date`, `icd10_codes: list[str]`                                                                                                     |
| `track_preferences_updated`       | `subject_id`                                                                               | `reading_level`, `tone`, `dietary_preferences`, `comfort_with_technology`, `energy_level`, `symptoms_need_help_managing`, `things_to_track`, `notification_preferences` |
| `track_emergency_contact_updated` | `subject_id`                                                                               | `name`, `relationship`, `phone`, `email`                                                                                                                                |
| `track_care_team_updated`         | `subject_id`, `members: list[CareTeamMember]`                                              | —                                                                                                                                                                       |
| `track_insurance_updated`         | `subject_id`                                                                               | `payer`, `plan_name`, `member_id`, `group_id`                                                                                                                           |
| `track_social_updated`            | `subject_id`                                                                               | `living_situation`, `support_system`, `transportation_access`, `employment_status`, `housing_stability`                                                                 |
| `track_pharmacy_updated`          | `subject_id`                                                                               | `name`, `address`, `phone`                                                                                                                                              |
| `track_treatment_phase_changed`   | `subject_id`, `new_phase: str`, `effective_date: str`, `changed_by: 'clinician'\|'system'` | `previous_phase: str`                                                                                                                                                   |

```python
class CareTeamMember(TypedDict):
    action: str    # 'add'|'update'|'remove'
    role: str
    name: NotRequired[str]
    npi: NotRequired[str]   # preferred identifier for matching
    organization: NotRequired[str]
```

**Example:**

```python
client.track_demographics_updated(
    subject_id="p_abc123",
    dob="1972-04-15",
    sex="female",
    language="en",
    address={
        "street": "123 Maple St",
        "city": "Boston",
        "state": "MA",
        "zip": "02101",
        "country": "US",
    },
)
```

---

## 6. Ingestion API Endpoints

The SDK targets the existing `app-api` surface via a dedicated SDK router at `services/app-api/routes/sdk/`, mirroring `services/app-api/routes/mcp/`.

Organisation identity is derived entirely from the API key — every request carries `Authorization: Bearer olira_{env}_{key}` and the server resolves the org server-side. Customers never include an `org_id` in the payload.

| Method | Path               | Purpose                            |
| ------ | ------------------ | ---------------------------------- |
| `POST` | `/v1/events`       | Single event                       |
| `POST` | `/v1/events/batch` | Batch of up to `batch_size` events |

### Single Event Request

```json
{
  "event_name": "symptom_esas_report",
  "subject_id": "p_123_pseudo",
  "timestamp": "2026-02-26T08:15:00Z",
  "event_id": "e1a2b3c4-...",
  "idempotency_key": "c6f8b1...",
  "properties": { ... },
  "context": { ... }
}
```

### Batch Request

```json
{ "events": [ ... ] }
```

### Batch Response

```json
{
  "accepted": 48,
  "failed": 2,
  "errors": [
    {
      "index": 3,
      "status": "error",
      "code": "validation_error",
      "message": "subject_id required"
    }
  ]
}
```

Partial batch failures: the SDK logs dropped events (event_name only, no payload content) and invokes the `on_error` callback if configured.

---

## 7. Delivery & Reliability

### Default: Non-Blocking Background Queue

- `track_*` recorders enqueue events immediately and return without blocking the caller.
- A background worker thread batches and flushes every `flush_interval` seconds or when the queue reaches `batch_size` events.
- Best-effort delivery: events retried up to `max_retries` times with exponential backoff.
- Queue bounded at `max_queue_size`; new events dropped (with `on_error` notification) when full.
- `atexit` hook calls `flush()` automatically on interpreter shutdown.
- `flush()` is **blocking** — it waits until all queued events have been delivered (or permanently failed) over the network before returning. This is required for the `atexit` hook and short-lived scripts to work reliably.

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

### Serverless / Lambda Pattern

```python
client = OliraClient(api_key=..., async_flush=False)
# track() blocks and flushes synchronously — no background thread
```

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
    client.track_symptom_esas(subject_id="p_123", symptoms=[...])
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
| Payload logging        | Event bodies are **never** written to logs. Only `event_name`, first 8 chars of `subject_id`, and batch metadata logged at `DEBUG` level via the standard Python `logging` module under the logger name `olira`. Silence or redirect with standard Python logging config.                                                                |
| API key redaction      | Keys always masked as `olira_***` in all output.                                                                                                                                                                                                                                                                                         |
| `subject_id` PII guard | `ValidationError` raised if value matches email, 10-digit phone, or SSN pattern.                                                                                                                                                                                                                                                         |
| Max payload size       | 512 KB per event hard limit — events exceeding this raise `ValidationError` before any network call. For `track_clinical_note` specifically, if the payload exceeds 512 KB the SDK raises `ValidationError` with a message indicating the note is too large; the caller is responsible for truncating or chunking. No silent truncation. |
| Documentation warnings | All public docs and docstrings clearly warn against sending direct patient identifiers.                                                                                                                                                                                                                                                  |

Customers are responsible for pseudonymisation upstream. A future validator version may detect additional PII patterns.

### 9.2 Server-side (Olira's infrastructure)

This is separate from SDK-side logging. Every event that reaches Olira's ingestion API is stored in full and is the basis for provenance and audit trails.

| Concern            | Behaviour                                                                                                                    |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Full event storage | The complete event payload is stored server-side, including all clinical fields, timestamps, and metadata.                   |
| Provenance         | Each event is traceable by `event_id`, `idempotency_key`, `subject_id`, org (derived from API key), and ingestion timestamp. |
| Audit trail        | The server-side record is the authoritative log of what data was submitted, by which organisation, and when.                 |
| Deduplication      | `idempotency_key` prevents duplicate events from appearing in the audit trail on retries.                                    |

> Customers operating in regulated environments (HIPAA covered entities, etc.) should refer to Olira's data processing agreement for retention periods, access controls, and BAA terms. The SDK itself is the delivery mechanism — compliance obligations are governed at the platform level.

---

## 10. Packaging & Distribution

### Package Structure

```
packages/olira-sdk-python/
  src/olira/
    __init__.py          # public API: init, flush, event recorders, OliraClient, exceptions
    client.py            # OliraClient class (sync); AsyncOliraClient class
    queue.py             # BackgroundWorker, bounded queue
    http.py              # HTTP transport, retry logic
    models.py            # Event recorder schemas (Pydantic v2 or TypedDict)
    exceptions.py        # Typed exception hierarchy
    py.typed             # PEP 561 marker
  tests/
    test_client.py
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
- `src/olira/__init__.py` — bump `__version__`
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

## Appendix: Full Event Catalogue

Complete list of all event types with their `event_name` strings, categories, payload shapes, and field-level notes.

**Source of truth:** Event types are derived from two authoritative sources in this repository:

- `EventLogType` enum in `packages/common-models/src/olira_common_models/foundation/shared/enums.py` — the canonical list of all event names the server recognises.
- `services/app-api/docs/event_log_type_definition.md` — field-level payload definitions for each event type.

Events generated internally by the platform (e.g. from the mobile app or internal pipelines) are defined in those sources but intentionally excluded from this SDK catalogue — the SDK only exposes events that external customer applications are expected to produce. Profile events are included here because they are required to populate `StableData`, a core section of the Patient State initialised at user creation time.

Fields marked `†` are computed server-side and must never be sent by clients.

---

### A.1 Symptom Reports (`symptom_reports`)

#### `symptom_ctcae_grade`

Records CTCAE or PRO-CTCAE symptom grades.

| Field                     | Type                   | Required | Notes                                      |
| ------------------------- | ---------------------- | -------- | ------------------------------------------ |
| `instrument`              | `'ctcae'\|'pro_ctcae'` | No       | Defaults to `'ctcae'`                      |
| `recall_period_days`      | `int`                  | No       | —                                          |
| `symptoms`                | `list[CtcaeSymptom]`   | Yes      | At least one item                          |
| `symptoms[].type`         | `str`                  | Yes      | Symptom name                               |
| `symptoms[].grade`        | `int`                  | Yes      | 0–5 (ctcae); 0–4 per dimension (pro_ctcae) |
| `symptoms[].frequency`    | `int`                  | No       | PRO-CTCAE only (0–4)                       |
| `symptoms[].interference` | `int`                  | No       | PRO-CTCAE only (0–4)                       |
| `symptoms[].onset`        | `str`                  | No       | ISO 8601 datetime                          |
| `symptoms[].snomed_code`  | `str`                  | No       | SNOMED CT preferred                        |
| `symptoms[].meddra_code`  | `str`                  | No       | MedDRA secondary                           |

---

#### `symptom_esas_report`

Patient-reported symptom burden using ESAS-r (Edmonton Symptom Assessment System Revised).

| Field                       | Type                | Required  | Notes                                                                                                     |
| --------------------------- | ------------------- | --------- | --------------------------------------------------------------------------------------------------------- |
| `symptoms`                  | `list[EsasItem]`    | Yes       | 1–10 items                                                                                                |
| `symptoms[].name`           | `str`               | Yes       | pain, tiredness, nausea, depression, anxiety, drowsiness, appetite, wellbeing, shortness_of_breath, other |
| `symptoms[].score`          | `int`               | Yes       | 0–10                                                                                                      |
| `total_score`               | `int`               | †Computed | Auto-computed by SDK from sum; override accepted                                                          |
| `subscale_scores.physical`  | `int`               | †Computed | Server-side                                                                                               |
| `subscale_scores.emotional` | `int`               | †Computed | Server-side                                                                                               |
| `subscale_scores.wellbeing` | `int`               | †Computed | Server-side                                                                                               |
| `recall_period`             | `'now'\|'past_24h'` | No        | —                                                                                                         |

---

#### `symptom_custom_report`

Custom or non-standard instrument symptom report.

| Field                    | Type                      | Required | Notes                      |
| ------------------------ | ------------------------- | -------- | -------------------------- |
| `instrument`             | `str`                     | No       | Instrument name/identifier |
| `symptoms`               | `list[CustomSymptomItem]` | Yes      | At least one item          |
| `symptoms[].type`        | `str`                     | Yes      | Symptom type key           |
| `symptoms[].name`        | `str`                     | Yes      | Display name               |
| `symptoms[].score`       | `float`                   | Yes      | —                          |
| `symptoms[].scale_min`   | `float`                   | No       | —                          |
| `symptoms[].scale_max`   | `float`                   | No       | —                          |
| `symptoms[].snomed_code` | `str`                     | No       | —                          |
| `symptoms[].meddra_code` | `str`                     | No       | —                          |

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
| `symptom_type` | `str` | Yes      | Symptom name/key                                                                |
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

#### `medication_added`

Medication added to a patient's medication list.

| Field                                    | Type                   | Required  | Notes                                           |
| ---------------------------------------- | ---------------------- | --------- | ----------------------------------------------- |
| `medications`                            | `list[MedicationItem]` | Yes       | See schema in Section 5.6                       |
| `medications[].rxnorm_cui`               | `str`                  | Cond.     | Preferred; one of rxnorm_cui or medication_name |
| `medications[].medication_name`          | `str`                  | Cond.     | Fallback                                        |
| `medications[].dose`                     | `float`                | No        | —                                               |
| `medications[].dose_unit`                | `str`                  | No        | —                                               |
| `medications[].frequency`                | `str`                  | No        | —                                               |
| `medications[].route`                    | `str`                  | No        | —                                               |
| `medications[].form`                     | `str`                  | No        | —                                               |
| `medications[].start_date`               | `str`                  | No        | ISO 8601 date                                   |
| `medications[].schedule_times`           | `list[str]`            | No        | HH:MM strings; triggers adherence tracking      |
| `medications[].adherence_window_minutes` | `int`                  | No        | Default 60                                      |
| `medications[].prescribed_by.npi`        | `str`                  | No        | —                                               |
| `therapeutic_class` †                    | `str`                  | †Computed | Resolved from RxNorm server-side                |

---

#### `medication_updated`

Existing medication details changed. Patch-style: include identifier + only changed fields.

| Field                           | Type                    | Required | Notes                      |
| ------------------------------- | ----------------------- | -------- | -------------------------- |
| `medications`                   | `list[MedicationPatch]` | Yes      | —                          |
| `medications[].rxnorm_cui`      | `str`                   | Cond.    | Identifier for matching    |
| `medications[].medication_name` | `str`                   | Cond.    | Fallback identifier        |
| (any MedicationItem field)      |                         | No       | Only changed fields needed |

See `MedicationPatch` schema in Section 5.6.

---

#### `medication_deleted`

Medication removed from patient's list.

| Field                           | Type                         | Required | Notes                |
| ------------------------------- | ---------------------------- | -------- | -------------------- |
| `medications`                   | `list[MedicationIdentifier]` | Yes      | —                    |
| `medications[].rxnorm_cui`      | `str`                        | Cond.    | Preferred identifier |
| `medications[].medication_name` | `str`                        | Cond.    | Fallback             |

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

All profile events are patch-style — include only the `subject_id` and fields that changed.

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

| Category        | `event_name` strings                                                                                                                                                                                       | Count  |
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

The 41 event types map to the event recorders in Section 5. Several recorders (e.g. `track_dose_taken` / `track_dose_skipped`) compose into a single underlying event (`medication_dose_update`), and a handful produce compound events with multiple sub-payloads, bringing the total recorder count above the raw event count.
