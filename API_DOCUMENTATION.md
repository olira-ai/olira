# Olira API Reference

The Olira API lets you manage patients, log health events, and mint patient-scoped access tokens. The Python SDK handles all HTTP details for you — if you're calling the API directly, see the cURL examples in the [Authentication](#authentication) section for the base URL.

---

## Getting Started

**Install the SDK:**

```bash
pip install olira
```

**First logged event — complete path from zero:**

```python
import olira
from olira import OliraEventType

# 1. Initialise once at application startup (reads OLIRA_API_KEY env var if api_key is omitted)
olira.init(api_key="olira_prod_...")

# 2. Create a patient — Olira assigns the id; store it for all future calls
from olira import OliraClient
client = OliraClient(api_key="olira_prod_...")
patient = client.create_patient(
    first_name="Jane",
    last_name="Smith",
    timezone="America/New_York",
)
patient_id = patient.id  # e.g. "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82" — persist this

# 3. Log an event
olira.log(event_type=OliraEventType.USER_LOGIN, patient_id=patient_id)

# 4. Flush before process exit to ensure all queued events are delivered
olira.flush()
```

> `patient.id` is Olira-assigned — you cannot choose it. Persist it in your database so you can reference the same patient in future calls.

---

## Authentication

All Olira API requests are authenticated using an `Authorization: Bearer <token>` header. There are two types of tokens, each suited to a different context.

### API Keys — server-side use

API keys are long-lived credentials tied to your organisation. They are the primary way to call the API from your backend. Create one in the [Olira Console](https://console.olira.ai) under **Settings → API Keys**, or with the CLI:

```bash
olira keys create --name "My Backend" --scopes api:manage-patients sdk:event-log sdk:patient-token
```

Copy the key when shown — it is **not displayed again**. Pass it as a Bearer token on every request:

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")
```

```bash
curl https://api.prod.olira.ai/v1/patients \
  --header "Authorization: Bearer olira_prod_..."
```

Use `olira_dev_...` keys against the development environment (`https://api.dev.olira.ai`).

Organisation context is resolved server-side from the key — you never pass an `org_id` in request bodies or query parameters.

> **Keep API keys server-side.** Do not embed them in mobile apps, browser JavaScript, or any client-side code. For patient-facing clients, use a Patient Token instead (see below).

---

### Patient Tokens — client-side use

A Patient Token is a short-lived JWT (15 minutes) scoped to a single patient. It is designed for situations where a patient device or frontend needs to call Olira directly — for example, when connecting to the **MCP Patient State server** from a mobile app or AI tool.

The flow is:

```
Your backend ──── POST /v1/auth/token ────► Olira API
                  { patient_id: "8a4fde23-0f1b-..." }   (API key, sdk:patient-token scope)
                  ◄────── { access_token, expires_in: 900 }

Your backend ──── forward token ──────────► Patient device / AI tool
                                            │
                                            └── uses token as Bearer credential
                                                (locked to patient id, read-only)
```

Mint a token from your backend using the SDK:

```python
from olira import OliraClient

# Your backend — API key with sdk:patient-token scope
client = OliraClient(api_key="olira_prod_...")
token = client.get_patient_token(patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82")

# Forward token.access_token to the patient device.
# The device uses it as: Authorization: Bearer <token.access_token>
```

The token is locked to the patient on the server — the recipient cannot access any other patient's data, and the token expires automatically after `expires_in` seconds.

---

### Auth error responses

| Status | Cause |
|---|---|
| `401 Unauthorized` | Missing `Authorization` header, malformed key format, or revoked key |
| `403 Forbidden` | Valid key but missing the required scope for this endpoint |

---

## Olira CLI

The **Olira CLI** (`olira`) is a companion tool that handles authentication and API key management without needing to open the Console in a browser. Install it once and use it to create keys, check your identity, and configure MCP access.

> **Prerequisites:** You need an Olira account before using the CLI. Sign up or log in at [console.olira.ai](https://console.olira.ai).

**Install (macOS / Linux — Homebrew, recommended):**

```bash
brew install raiahealth/tap/olira
```

**Install via shell script:**

```bash
curl -fsSL https://install.olira.ai | sh
```

**Verify:**

```bash
olira --version
```

### Creating an API key with the CLI

```bash
# Interactive wizard — prompts for name and scope selection
olira keys create

# Non-interactive (for scripting / CI)
olira keys create --name "My Backend" --scopes api:manage-patients sdk:patient-token sdk:event-log
```

Copy the key when shown — it is **not displayed again**. API keys never expire and can be revoked at any time with `olira keys revoke <name-or-id>`.

### Other useful commands

| Command | Description |
|---|---|
| `olira login` | Log in via browser (opens Auth0) |
| `olira status` | Show current identity, org, and token expiry |
| `olira keys list` | List all API keys for your organisation and their scopes |
| `olira keys revoke <name>` | Permanently revoke a key |
| `olira configure cursor` | Write the MCP Patient State entry into `.cursor/mcp.json` |
| `olira logout` | Remove local credentials and wipe MCP config |

> The CLI is the fastest way to set up a new integration. Run `olira keys create`, paste the resulting key into your application as `OLIRA_API_KEY`, and you're ready to make API calls.

---

## Scopes

Each API key is assigned one or more scopes at creation time. Use the minimum set of scopes required for the key's purpose — in particular, keep `api:manage-patients` and `sdk:patient-token` out of client-side or device-embedded keys.

| Scope | Endpoints |
|---|---|
| `sdk:event-log` | `POST /v1/events`, `POST /v1/events/batch` |
| `sdk:event-management` | `GET /v1/events`, `DELETE /v1/events` |
| `api:manage-patients` | `POST /v1/patients`, `GET /v1/patients`, `GET /v1/patients/{patient_id}`, `PUT /v1/patients/{patient_id}`, `DELETE /v1/patients/{patient_id}` |
| `sdk:patient-token` | `POST /v1/auth/token` |

---

## Models

Typed reference for every SDK model. Import these directly from the `olira` package.

---

### `ExternalIdentifier`

Links a patient to their ID in an external system. Used in `CreatePatientRequest`, `UpdatePatientRequest`, and `Patient`.

| Field | Type | Description |
|---|---|---|
| `system` | `str` | System name, e.g. `"epic"`, `"flatiron"`, `"fhir"` |
| `value` | `str` | Patient ID in that system (MRN, FHIR id, etc.) |

---

### `Patient`

Returned by all patient endpoints.

`id` is the Olira-assigned identifier for this patient, returned at creation time. Use it in all subsequent calls that reference this patient.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Olira-assigned identifier for this patient |
| `first_name` | `str` | |
| `last_name` | `str` | |
| `sex` | `str` | `"male"`, `"female"`, or `"unknown"` |
| `timezone` | `str` | IANA timezone string, e.g. `"America/Los_Angeles"` |
| `status` | `str` | `"pending"`, `"active"`, or `"deleted"` |
| `email` | `str \| None` | |
| `phone_number` | `str \| None` | |
| `date_of_birth` | `str \| None` | ISO 8601 datetime string |
| `primary_disease_site` | `str \| None` | e.g. `"breast"`, `"lung"` |
| `disease_stage` | `str \| None` | e.g. `"II"`, `"IIIa"` |
| `created_at` | `str \| None` | ISO 8601 datetime of patient creation |
| `external_identifiers` | `list[ExternalIdentifier]` | IDs in external systems; empty list if none |
| `metadata` | `dict \| None` | Arbitrary key-value store; `null` if not set |

---

### `PatientListResult`

Returned by `GET /v1/patients`.

| Field | Type | Description |
|---|---|---|
| `patients` | `list[Patient]` | Page of results |
| `total` | `int` | Total patients in the organisation (across all pages) |
| `has_more` | `bool` | `true` if more results exist beyond this page |

---

### `PatientToken`

Returned by `POST /v1/auth/token`.

| Field | Type | Description |
|---|---|---|
| `access_token` | `str` | RS256-signed JWT. Pass as `Authorization: Bearer <token>` to the MCP Patient State server |
| `token_type` | `str` | Always `"bearer"` |
| `expires_in` | `int` | Seconds until expiry (always `900` — 15 minutes) |
| `scopes` | `list[str]` | Always `["mcp:patient-state"]` |

---

### `EventSpec`

Input to `log_batch()`. One per event in the batch.

| Field | Type | Required | Description |
|---|---|---|---|
| `event_type` | `OliraEventType` | Yes | Event category |
| `patient_id` | `str` | Yes | Olira-assigned patient id (the `id` from `Patient`) |
| `payload` | `dict \| None` | No | Event-specific data |
| `trace` | `OliraTrace \| None` | No | Link the event to an object in your system (e.g. a conversation or message) |
| `timestamp` | `str \| None` | No | ISO 8601 event occurrence time. Defaults to ingestion time |
| `idempotency_key` | `str \| None` | No | Deduplication key (UUID recommended) |

---

### `OliraTrace`

Links an event to an object inside Olira (e.g. a conversation or message). Used in both `EventSpec` and `EventRecord`.

| Field | Type | Description |
|---|---|---|
| `object_type` | `str` | e.g. `"conversation"`, `"message"` |
| `object_id` | `str` | Your identifier for the linked object (e.g. a conversation ID in your system) |

---

### `BatchResult`

Returned by `log_batch()` / `POST /v1/events/batch`.

| Field | Type | Description |
|---|---|---|
| `accepted` | `int` | Number of events successfully ingested |
| `failed` | `int` | Number of events rejected |
| `errors` | `list[BatchError]` | Per-event error detail; empty when `failed == 0` |

---

### `BatchError`

One entry per rejected event in a batch.

| Field | Type | Description |
|---|---|---|
| `index` | `int` | Zero-based position of the failed event in the request array |
| `code` | `str` | Machine-readable error code, e.g. `"validation_error"`, `"patient_not_found"` |
| `message` | `str` | Human-readable description |

---

### `EventRecord`

One event returned by `GET /v1/events`.

| Field | Type | Description |
|---|---|---|
| `event_id` | `str` | UUID assigned at ingestion. Stable — use for `delete_events(event_ids=...)` |
| `event_type` | `OliraEventType` | |
| `patient_id` | `str` | Your identifier for the patient |
| `timestamp` | `str` | ISO 8601 event occurrence time |
| `ingested_at` | `str` | ISO 8601 server ingestion time |
| `payload` | `dict` | Event payload as submitted |
| `trace` | `OliraTrace \| None` | Present only when the event was logged with a trace |

---

### `EventQueryResult`

Returned by `GET /v1/events`.

| Field | Type | Description |
|---|---|---|
| `events` | `list[EventRecord]` | Page of results |
| `total` | `int` | Total matching events (across all pages) |
| `has_more` | `bool` | `true` if more results exist beyond this page |

---

### `DeleteResult`

Returned by `DELETE /v1/events`.

| Field | Type | Description |
|---|---|---|
| `deleted_count` | `int` | Number of events permanently removed |
| `patient_id` | `str` | The patient ID from the request, echoed back |

---

### `OliraEventType`

String enum. All values are lowercase with underscores.

**Symptom reports**

| Value | Description |
|---|---|
| `symptom_report` | Structured symptom severity with a defined instrument (`esas_r`, `pro_ctcae`, `ctcae`, `custom`). Pass `instrument` in the payload |
| `symptom_free_text` | Free-text symptom description (processed by extraction) |
| `symptom_detail` | Follow-up detail on an already-reported symptom |
| `moods_report` | Categorical mood or emotion labels |
| `functional_class_reported` | Functional classification (NYHA, ECOG, Karnofsky, etc.) |
| `health_metric_reported` | Single scalar patient-reported metric with an explicit scale |

**Lab & Clinical**

| Value | Description |
|---|---|
| `lab_results_received` | Laboratory test results (blood, urine, etc.) |
| `vitals_measurement` | Vital signs (BP, HR, SpO2, temp, etc.) |
| `clinical_note_received` | Provider-authored clinical note with structured sections |
| `clinical_finding_reported` | Discrete clinical finding from exam or assessment |
| `procedure_result_received` | Pathology or procedure result narrative |
| `genomic_variant_reported` | Genomic or molecular variants |
| `imaging_result_received` | Imaging study findings (CT, MRI, PET, etc.) |
| `clinical_measurement_reported` | Non-lab clinical measurements (ejection fraction, tumour diameter, ECOG score, etc.) |
| `treatment_response_assessment_reported` | Treatment response assessment (CR, PR, SD, PD, etc.) |
| `clinical_plan_item_reported` | Discrete future plan items (orders, referrals, scheduled procedures) |
| `care_encounter_reported` | Care encounters or visits |
| `unstructured_report_received` | Raw document payload for extraction (OCR, PDF, EHR export) |

**Questionnaires**

| Value | Description |
|---|---|
| `questionnaire_response` | Full questionnaire or instrument submission (PHQ-9, GAD-7, etc.) |
| `questionnaire_item_response` | Single question-and-answer pair |

**Conversations**

| Value | Description |
|---|---|
| `conversation_completed` | End of a chat or voice conversation (with transcript) |
| `conversation_turn_logged` | Single turn within an ongoing conversation |

**Passive data**

| Value | Description |
|---|---|
| `heart_rate_data_received` | Heart rate / HRV data from a device |
| `sleep_data_received` | Sleep session data |
| `activity_data_received` | Steps / activity / calorie data |
| `cgm_reading_received` | Continuous glucose monitor reading |
| `spo2_reading_received` | Blood oxygen saturation reading |
| `weight_measurement_received` | Body weight from a connected scale |

**Medications**

| Value | Description |
|---|---|
| `medication_action` | Add, update, or remove medications from the patient's list. Pass `action: "add" \| "update" \| "delete"` per item |
| `medication_dose_update` | Dose taken or skipped |
| `medication_adverse_event_reported` | Medication-related adverse event or side effect |

**Engagement**

| Value | Description |
|---|---|
| `user_login` | Patient logged in |
| `user_logout` | Patient logged out |
| `content_interacted` | Patient interacted with a content item |
| `notification_interacted` | Patient acted on a push notification |
| `task_updated` | Task completed or skipped |
| `interaction_feedback` | Explicit feedback given by patient |
| `feature_used` | Feature usage tracked |

**Profile**

| Value | Description |
|---|---|
| `demographics_updated` | Name, DOB, sex, address, language, etc. |
| `condition_updated` | Diagnosis or disease (disease_type, stage) |
| `preferences_updated` | Reading level, tone, dietary, notifications |
| `emergency_contact_updated` | Emergency contact details |
| `care_team_updated` | Providers added, updated, or removed |
| `insurance_updated` | Insurance / payer details |
| `social_updated` | Social determinants of health |
| `pharmacy_updated` | Preferred pharmacy |
| `treatment_phase_changed` | Treatment phase transition (active_treatment, surveillance, palliative, remission) |

---

## Patients

All patient endpoints require the `api:manage-patients` scope and accept a raw API key (not a JWT) as the Bearer token.

`{patient_id}` in all paths is the Olira-assigned `id` returned in the `Patient` object when you called `POST /v1/patients`.

---

### Create a patient

**`POST /v1/patients`**

Creates a new patient in your organisation. Olira assigns a stable `id` at creation time — store it to reference this patient in all subsequent calls.

**Authorization:** `api:manage-patients` scope

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `first_name` | `str` | **Yes** | |
| `last_name` | `str` | **Yes** | |
| `timezone` | `str` | **Yes** | IANA timezone string, e.g. `"America/Los_Angeles"` |
| `email` | `str \| null` | No | |
| `phone_number` | `str \| null` | No | |
| `date_of_birth` | `str \| null` | No | ISO 8601 datetime, e.g. `"1985-03-22T00:00:00Z"` |
| `sex` | `str` | No | `"male"`, `"female"`, or `"unknown"` (default) |
| `primary_disease_site` | `str \| null` | No | e.g. `"breast"`, `"lung"` |
| `disease_stage` | `str \| null` | No | e.g. `"II"`, `"IIIa"` |
| `external_identifiers` | `list[ExternalIdentifier]` | No | IDs in external systems (default `[]`). Max 20 per patient. Each `(system, value)` pair must be unique within your organisation |
| `metadata` | `dict \| null` | No | Arbitrary key-value store. Keys must not start with `olira_`. Max 50 keys, ≤ 8 KB total. Values must be scalars (no nested objects) |

**Response** `201 Created` → [`Patient`](#patient)

```json
{
  "id": "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
  "first_name": "Jane",
  "last_name": "Smith",
  "email": "jane@example.com",
  "phone_number": null,
  "date_of_birth": "1985-03-22T00:00:00+00:00",
  "sex": "female",
  "timezone": "America/New_York",
  "status": "pending",
  "primary_disease_site": "breast",
  "disease_stage": "II",
  "created_at": "2026-03-01T12:00:00+00:00"
}
```

**Python**

```python
from olira import OliraClient, ExternalIdentifier

client = OliraClient(api_key="olira_prod_...")

# timezone is required; id is auto-generated — store patient.id to reference this patient later
patient = client.create_patient(
    first_name="Jane",
    last_name="Smith",
    email="jane@example.com",
    timezone="America/Los_Angeles",
    primary_disease_site="breast",
    disease_stage="II",
    external_identifiers=[ExternalIdentifier(system="epic", value="MRN-00042")],
    metadata={"trial_arm": "A", "enrolled_by_npi": "1234567890"},
)
print(patient.id, patient.status)  # "8a4fde23-0f1b-4c2a-..." "pending"
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `api:manage-patients` scope |
| `409 Conflict` | An `(external_system, external_value)` pair already exists in your organisation |
| `422 Unprocessable Entity` | `first_name`, `last_name`, or `timezone` missing; `date_of_birth` not valid ISO 8601; `metadata` constraint violated |

---

### List patients

**`GET /v1/patients`**

Returns all non-deleted patients in your organisation that were created via the SDK. Results are sorted by first name.

**Authorization:** `api:manage-patients` scope

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | `int` | `100` | Maximum number of patients to return. Range: 1–100 |
| `offset` | `int` | `0` | Number of patients to skip (for pagination) |
| `external_system` | `str` | — | Filter by external system name (must be used together with `external_value`) |
| `external_value` | `str` | — | Filter by external system value (must be used together with `external_system`) |

**Response** `200 OK` → [`PatientListResult`](#patientlistresult)

```json
{
  "patients": [
    {
      "id": "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
      "first_name": "Jane",
      "last_name": "Smith",
      "email": "jane@example.com",
      "phone_number": null,
      "date_of_birth": "1985-03-22T00:00:00+00:00",
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

**Python**

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")

result = client.list_patients(limit=50, offset=0)
print(f"{result.total} patients, has_more={result.has_more}")
for patient in result.patients:
    print(patient.id, patient.first_name, patient.last_name)

# Lookup by external identifier
result = client.list_patients(external_system="epic", external_value="MRN-00042")
assert len(result.patients) == 1
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `api:manage-patients` scope |

---

### Get a patient

**`GET /v1/patients/{patient_id}`**

Returns a single patient by their id.

**Authorization:** `api:manage-patients` scope

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `patient_id` | `str` | Olira-assigned patient id (from `Patient.id`) |

**Response** `200 OK` → [`Patient`](#patient)

```json
{
  "id": "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
  "first_name": "Jane",
  "last_name": "Smith",
  "email": "jane@example.com",
  "phone_number": null,
  "date_of_birth": "1985-03-22T00:00:00+00:00",
  "sex": "female",
  "timezone": "America/New_York",
  "status": "pending",
  "primary_disease_site": "breast",
  "disease_stage": "II",
  "created_at": "2026-03-01T12:00:00+00:00"
}
```

**Python**

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")

patient = client.get_patient(patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82")
print(patient.status)
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `api:manage-patients` scope |
| `404 Not Found` | No patient with this id in your organisation, or patient has been deleted |

---

### Update a patient

**`PUT /v1/patients/{patient_id}`**

Partially updates a patient. Only the fields you include in the request body are changed — omitted fields are left as-is.

**Authorization:** `api:manage-patients` scope

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `patient_id` | `str` | Olira-assigned patient id (from `Patient.id`) |

**Request body** (all fields optional)

| Field | Type | Description |
|---|---|---|
| `first_name` | `str \| null` | |
| `last_name` | `str \| null` | |
| `email` | `str \| null` | |
| `phone_number` | `str \| null` | |
| `sex` | `str \| null` | `"male"`, `"female"`, or `"unknown"` |
| `timezone` | `str \| null` | IANA timezone string |
| `primary_disease_site` | `str \| null` | |
| `disease_stage` | `str \| null` | |
| `external_identifiers` | `list[ExternalIdentifier] \| null` | Full replace — omit to leave as-is; pass `[]` to clear all |
| `metadata` | `dict \| null` | Full replace — omit to leave as-is; pass `{}` to clear |

**Response** `200 OK` → [`Patient`](#patient) (full updated record)

```json
{
  "id": "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
  "first_name": "Jane",
  "last_name": "Smith",
  "email": "jane@example.com",
  "phone_number": null,
  "date_of_birth": "1985-03-22T00:00:00+00:00",
  "sex": "female",
  "timezone": "America/New_York",
  "status": "pending",
  "primary_disease_site": "breast",
  "disease_stage": "III",
  "created_at": "2026-03-01T12:00:00+00:00"
}
```

**Python**

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")

patient = client.update_patient(
    patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
    disease_stage="III",
)
print(patient.disease_stage)  # "III"
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `api:manage-patients` scope |
| `404 Not Found` | No patient with this id in your organisation, or patient has been deleted |
| `409 Conflict` | An `(external_system, external_value)` pair in `external_identifiers` already exists in your organisation |

---

### External Identifiers

`external_identifiers` links a patient to their ID in an external system, enabling round-trip lookups without a side table.

**Common use cases:**
- Storing an Epic MRN: `ExternalIdentifier(system="epic", value="MRN-00042")`
- Storing a Flatiron patient ID: `ExternalIdentifier(system="flatiron", value="FLT-9999")`
- Storing a FHIR resource ID: `ExternalIdentifier(system="fhir", value="Patient/abc123")`

**Lookup pattern:**
```python
# Find a patient by their Epic MRN
result = client.list_patients(external_system="epic", external_value="MRN-00042")
patient = result.patients[0]
```

**Constraints (enforced server-side):**
- Max 20 `external_identifiers` per patient
- Each `(system, value)` pair must be unique within your organisation — duplicate submissions return `409 Conflict`

---

### Delete a patient

**`DELETE /v1/patients/{patient_id}`**

Soft-deletes a patient. The patient's status is set to `"deleted"` and they are excluded from list results and future API calls.

**Authorization:** `api:manage-patients` scope

**Path parameters**

| Parameter | Type | Description |
|---|---|---|
| `patient_id` | `str` | Olira-assigned patient id (from `Patient.id`) |

**Response** `200 OK`

```json
{ "ok": true }
```

**Python**

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")

client.delete_patient(patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82")
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `api:manage-patients` scope |
| `404 Not Found` | No patient with this id in your organisation, or patient already deleted |

---

### Batch create patients

**`POST /v1/patients/batch`**

Creates up to **500** patients in a single request. Partial success is supported — if some patients fail, the rest are still created. The response lists each success in `items` and each failure in `errors`, both keyed by zero-based `index` matching the input array.

**Authorization:** `api:manage-patients` scope

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `patients` | `list[CreatePatientRequest]` | **Yes** | 1–500 patient objects. Each object has the same fields as `POST /v1/patients` |

**Response** `200 OK`

| Field | Type | Description |
|---|---|---|
| `count` | `int` | Total patients submitted (accepted + failed) |
| `items` | `list` | Successfully created patients |
| `items[].index` | `int` | Zero-based position in the input array |
| `items[].id` | `str` | Olira-assigned patient id |
| `items[].source` | `str \| null` | First `external_identifiers[0].system`, or `null` if none provided |
| `errors` | `list` | Patients that failed to create |
| `errors[].index` | `int` | Zero-based position in the input array |
| `errors[].code` | `str` | Machine-readable error code (see table below) |
| `errors[].message` | `str` | Human-readable description |

**Error codes**

| Code | Meaning |
|---|---|
| `conflict` | `external_identifier (system, value)` already exists in your organisation |
| `validation_error` | Invalid field value (e.g. malformed `date_of_birth`) |
| `server_error` | Unexpected server-side failure |

**Example request**

```python
from olira import OliraClient, CreatePatientRequest, ExternalIdentifier

client = OliraClient(api_key="olira_prod_...")

patients = [
    CreatePatientRequest(
        first_name="Jane",
        last_name="Smith",
        timezone="America/New_York",
        external_identifiers=[ExternalIdentifier(system="epic", value="MRN-001")],
    ),
    CreatePatientRequest(
        first_name="John",
        last_name="Doe",
        timezone="America/Chicago",
        external_identifiers=[ExternalIdentifier(system="flatiron", value="FLT-002")],
    ),
]

result = client.create_patients_batch(patients)
print(f"Created: {len(result.items)}, Failed: {len(result.errors)}")
for item in result.items:
    print(f"  [{item.index}] id={item.id} source={item.source}")
for err in result.errors:
    print(f"  [{err.index}] {err.code}: {err.message}")
```

**Example response**

```json
{
  "count": 2,
  "items": [
    { "index": 0, "id": "abc123...", "source": "epic" },
    { "index": 1, "id": "def456...", "source": "flatiron" }
  ],
  "errors": []
}
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `api:manage-patients` scope |
| `422 Unprocessable Entity` | More than 500 patients submitted, or invalid request body |

---

## Events

Event endpoints record health-related actions against a patient. The patient must exist (created via `POST /v1/patients` or the Console) before you can log events against them.

`patient_id` in every event request is the Olira-assigned `id` returned when the patient was created.

---

### Log a single event

**`POST /v1/events`**

Ingests one event. For high-throughput use cases prefer the batch endpoint. The SDK's `log()` method uses this endpoint when `async_flush=False`; otherwise events are automatically batched via `POST /v1/events/batch`.

**Authorization:** `sdk:event-log` scope

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `event_name` | `str` | **Yes** | Event type value from `OliraEventType`, e.g. `"user_login"` |
| `patient_id` | `str` | **Yes** | Olira-assigned patient id (the `id` from `Patient`). Must not be an email address, raw phone number, or SSN |
| `event_id` | `str \| null` | No | UUID for this event. Auto-generated if omitted. Stable identifier for targeted deletion |
| `idempotency_key` | `str \| null` | No | Deduplication key. Duplicate submissions with the same key are silently ignored |
| `timestamp` | `str \| null` | No | ISO 8601 event occurrence time. Defaults to server ingestion time if omitted |
| `payload` | `object` | No | Event-specific data. See event type catalogue in SPEC.md. Max 512 KB |
| `context` | `object` | No | SDK metadata (version, environment). Set automatically by the SDK client |
| `trace` | `object \| null` | No | Links the event to an Olira object — `{ "object_type": "...", "object_id": "..." }` |

**Response** `200 OK`

```json
{ "accepted": 1 }
```

**Python** (direct — synchronous)

```python
from olira import OliraClient, OliraEventType

client = OliraClient(api_key="olira_prod_...", async_flush=False)

client.log(
    event_type=OliraEventType.USER_LOGIN,
    patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
)
client.close()
```

**Python** (module-level singleton — recommended for long-running services)

```python
import olira
from olira import OliraEventType

# Call once at startup
olira.init(api_key="olira_prod_...")

# Then anywhere in your codebase — no client reference needed
olira.log(
    event_type=OliraEventType.USER_LOGIN,
    patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
)

# At process shutdown
olira.flush()
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `sdk:event-log` scope |
| `404 Not Found` | No patient with this `patient_id` in your organisation |
| `422 Unprocessable Entity` | Missing required fields or payload exceeds 512 KB |

---

### Log a batch of events

**`POST /v1/events/batch`**

Ingests up to `batch_size` events in a single request (default 50 per call when using `log_batch()`; up to whatever your server allows). Supports partial success — individual event failures do not abort the whole batch.

This is the endpoint used by the background worker that powers `log()`.

**Authorization:** `sdk:event-log` scope

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `events` | `array` | **Yes** | Array of event objects. Each has the same shape as the single-event request body |

```json
{
  "events": [
    {
      "event_name": "user_login",
      "patient_id": "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
      "event_id": "e1a2b3c4-0001-0000-0000-000000000001",
      "timestamp": "2026-03-01T09:00:00Z",
      "payload": {},
      "context": { "sdk_version": "0.1.0a4", "environment": "production" }
    },
    {
      "event_name": "symptom_report",
      "patient_id": "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
      "event_id": "e1a2b3c4-0001-0000-0000-000000000002",
      "timestamp": "2026-03-01T09:01:00Z",
      "payload": {
        "instrument": "esas_r",
        "symptoms": [{ "name": "pain", "score": 4 }]
      },
      "context": { "sdk_version": "0.1.0a4", "environment": "production" }
    }
  ]
}
```

**Response** `200 OK` → [`BatchResult`](#batchresult)

```json
{
  "accepted": 2,
  "failed": 0,
  "errors": []
}
```

Partial failure example:

```json
{
  "accepted": 1,
  "failed": 1,
  "errors": [
    {
      "index": 1,
      "code": "patient_not_found",
      "message": "Patient 'mrn-unknown' not found"
    }
  ]
}
```

**Python**

```python
from olira import OliraClient, EventSpec, OliraEventType, EsasItem

client = OliraClient(api_key="olira_prod_...")

result = client.log_batch([
    EventSpec(
        event_type=OliraEventType.USER_LOGIN,
        patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
    ),
    EventSpec(
        event_type=OliraEventType.SYMPTOM_REPORT,
        patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
        payload={
            "instrument": "esas_r",
            "symptoms": [EsasItem(name="pain", score=4).model_dump()],
        },
    ),
])
print(f"accepted={result.accepted}, failed={result.failed}")
client.close()
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `sdk:event-log` scope |
| `422 Unprocessable Entity` | Request body malformed (e.g. `events` field missing) |

Per-event failures (patient not found, payload too large, etc.) are returned inside the response body as `errors[]`, not as HTTP error codes.

---

### Query events

**`GET /v1/events`**

Returns events for a patient, filtered by event type and/or time range. Results are ordered by `timestamp` descending.

**Authorization:** `sdk:event-management` scope

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `patient_id` | `str` | **Yes** | Olira-assigned patient id (from `Patient.id`) |
| `event_type` | `str` | No | Filter to a single `OliraEventType` value, e.g. `"user_login"` |
| `from_timestamp` | `str` | No | Include events with `timestamp >=` this ISO 8601 value |
| `to_timestamp` | `str` | No | Include events with `timestamp <=` this ISO 8601 value |
| `ingested_after` | `str` | No | Include events with `ingested_at >` this ISO 8601 value |
| `ingested_before` | `str` | No | Include events with `ingested_at <` this ISO 8601 value |
| `limit` | `int` | No | Max results to return (default `100`) |
| `offset` | `int` | No | Results to skip for pagination (default `0`) |

Use `ingested_after` / `ingested_before` when you want to find events by when they arrived (e.g. "everything received in the last hour"). Use `from_timestamp` / `to_timestamp` to filter by when the event occurred in the real world.

**Response** `200 OK` → [`EventQueryResult`](#eventqueryresult)

```json
{
  "events": [
    {
      "event_id": "e1a2b3c4-0001-0000-0000-000000000002",
      "event_type": "symptom_report",
      "patient_id": "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
      "timestamp": "2026-03-01T09:01:00Z",
      "ingested_at": "2026-03-01T09:01:03Z",
      "payload": {
        "instrument": "esas_r",
        "symptoms": [{ "name": "pain", "score": 4 }]
      },
      "trace": null
    }
  ],
  "total": 1,
  "has_more": false
}
```

**Python**

```python
from olira import OliraClient, OliraEventType

client = OliraClient(api_key="olira_prod_...")

result = client.get_events(
    patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
    event_type=OliraEventType.SYMPTOM_REPORT,
    ingested_after="2026-03-01T00:00:00Z",
)
print(f"{result.total} events found")
for event in result.events:
    print(event.event_id, event.timestamp, event.payload)
client.close()
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `sdk:event-management` scope |
| `404 Not Found` | No patient with this `patient_id` in your organisation |

---

### Delete events

**`DELETE /v1/events`**

Permanently deletes events matching the given filters. At least one filter is required to prevent accidental deletion of all events for a patient.

**Authorization:** `sdk:event-management` scope

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `patient_id` | `str` | **Yes** | Olira-assigned patient id (from `Patient.id`) |
| `event_type` | `str \| null` | No* | Delete only events of this type |
| `from_timestamp` | `str \| null` | No* | Delete events with `timestamp >=` this ISO 8601 value |
| `to_timestamp` | `str \| null` | No* | Delete events with `timestamp <=` this ISO 8601 value |
| `ingested_after` | `str \| null` | No* | Delete events with `ingested_at >` this ISO 8601 value |
| `ingested_before` | `str \| null` | No* | Delete events with `ingested_at <` this ISO 8601 value |
| `event_ids` | `list[str] \| null` | No* | Delete specific events by their `event_id` UUIDs |

\* At least one of these filters must be provided. The SDK client enforces this client-side and raises `ValidationError` before making the request.

**Response** `200 OK` → [`DeleteResult`](#deleteresult)

```json
{
  "deleted_count": 3,
  "patient_id": "8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82"
}
```

**Python**

```python
from olira import OliraClient, OliraEventType

client = OliraClient(api_key="olira_prod_...")

# Delete all USER_LOGIN events for a patient
result = client.delete_events(
    patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
    event_type=OliraEventType.USER_LOGIN,
)
print(f"deleted {result.deleted_count} events")

# Delete specific events by ID
result = client.delete_events(
    patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82",
    event_ids=["e1a2b3c4-0001-...", "e1a2b3c4-0002-..."],
)
client.close()
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `sdk:event-management` scope |
| `404 Not Found` | No patient with this `patient_id` in your organisation |
| `422 Unprocessable Entity` | No filters provided (also raised client-side as `ValidationError`) |

---

## Patient Token

### Mint a patient-scoped JWT

**`POST /v1/auth/token`**

Exchanges an API key for a short-lived JWT locked to a single patient. The typical flow: your backend mints a token and forwards it to a patient device. The device uses the token with the Olira MCP Patient State server. The token enforces the patient binding server-side — the MCP ignores any `patient_id` passed in tool arguments and always uses the one embedded in the JWT.

```
Your backend ──── POST /v1/auth/token ────► Olira API
                  { patient_id: "8a4fde23-0f1b-..." }
                  ◄── { access_token, expires_in: 900 }

Your backend ──── forward token ──────────► Patient device
                                            │
                                            └── MCP Patient State server
                                                (locked to patient id)
```

**Authorization:** `sdk:patient-token` scope

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `patient_id` | `str` | **Yes** | Olira-assigned patient id (from `Patient.id`). The minted JWT grants access to this patient only |

**Response** `200 OK` → [`PatientToken`](#patienttoken)

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "scopes": ["mcp:patient-state"]
}
```

**Python**

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")  # must have sdk:patient-token scope

token = client.get_patient_token(patient_id="8a4fde23-0f1b-4c2a-9d7e-b36c1a5f0e82")

# Forward token.access_token to the patient device.
# The device uses it as: Authorization: Bearer <token.access_token>
print(f"expires in {token.expires_in}s, scopes={token.scopes}")
client.close()
```

**Error responses**

| Status | Cause |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Key does not have `sdk:patient-token` scope |
| `404 Not Found` | No patient with this `patient_id` in your organisation, or patient has been deleted |

---

## Error Handling

All SDK errors are subclasses of `OliraError`. Import the specific types you want to catch:

```python
from olira import AuthError, ValidationError, RateLimitError, ServerError

try:
    result = client.log_batch([...])
except AuthError:
    # Invalid or revoked API key, or missing scope
    raise
except RateLimitError as e:
    # Too many requests — retry after e.retry_after seconds
    time.sleep(e.retry_after)
except ValidationError:
    # Bad request — malformed payload, missing required field, etc.
    logging.error("Event rejected: %s", e)
except ServerError:
    # 5xx from Olira — SDK has already retried; escalate or queue for later
    raise
```

| Exception | When raised |
|---|---|
| `AuthError` | `401` or `403` response — invalid key, revoked key, or missing scope |
| `ValidationError` | `422` response or client-side pre-flight check (e.g. no filters on `delete_events`) |
| `RateLimitError` | `429` response — `e.retry_after` contains the seconds to wait |
| `ServerError` | `5xx` response after all retries are exhausted |

---

## Common Event Payloads

Quick reference for the four most-used event types. All payloads are passed as the `payload` dict to `client.log()` or inside `EventSpec`.

### `symptom_report`

```python
from olira import EsasItem

payload = {
    "instrument": "esas_r",
    "symptoms": [
        EsasItem(name="pain", score=3).model_dump(),
        EsasItem(name="fatigue", score=5).model_dump(),
        EsasItem(name="nausea", score=1).model_dump(),
    ],
}
client.log(event_type=OliraEventType.SYMPTOM_REPORT, patient_id=patient_id, payload=payload)
```

### `lab_results_received`

```python
payload = {
    "results": [
        {
            "test_name": "Hemoglobin",
            "value": 11.2,
            "unit": "g/dL",
            "reference_range": "12.0-16.0",
            "flag": "L",
        }
    ],
    "performing_lab": {"name": "Quest Diagnostics", "location": "New York, NY"},
    "collection_date": "2026-03-01",
}
client.log(event_type=OliraEventType.LAB_RESULTS_RECEIVED, patient_id=patient_id, payload=payload)
```

### `medication_action`

```python
payload = {
    "action": "add",
    "medications": [
        {
            "rxnorm_cui": "1049502",
            "medication_name": "Ondansetron 4mg",
            "dose": 4.0,
            "dose_unit": "mg",
            "frequency": "every_8h_as_needed",
            "route": "oral",
            "form": "tablet",
            "start_date": "2026-03-01",
        }
    ],
}
client.log(event_type=OliraEventType.MEDICATION_ACTION, patient_id=patient_id, payload=payload)
```

### `conversation_completed`

```python
payload = {
    "transcript": [
        {"role": "assistant", "content": "How are you feeling today?"},
        {"role": "user", "content": "I've had a headache since yesterday."},
        {"role": "assistant", "content": "I'm sorry to hear that. On a scale of 0–10, how severe is it?"},
        {"role": "user", "content": "About a 6."},
    ],
    "duration_seconds": 120,
}
client.log(event_type=OliraEventType.CONVERSATION_COMPLETED, patient_id=patient_id, payload=payload)
```
