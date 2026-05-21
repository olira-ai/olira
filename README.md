# Olira Python SDK

Log ingestion, patient management, historical backfill, and patient state client for the Olira platform.

## Install

```bash
pip install olira
```

## Documentation

Full API reference: [https://olira.ai/api-docs](https://olira.ai/api-docs) (Python SDK tab).

Local copy: [SDK_DOCUMENTATION.md](SDK_DOCUMENTATION.md).

---

## Authentication

All SDK methods authenticate with an **Olira API key** (`olira_prod_...`). Create keys from the Olira Console under **Settings → API Keys**, selecting the scopes you need:

| Scope                     | What it unlocks                                        |
| ------------------------- | ------------------------------------------------------ |
| `sdk:event-log`           | Log events                                             |
| `api:manage-patients`     | Create, read, update, delete patients                  |
| `sdk:patient-token`       | Mint short-lived patient-scoped JWTs                   |
| `sdk:historical-ingest`   | Create and manage historical data ingestion jobs       |
| `sdk:state-read`          | Read Patient State (modules, views, logs, memories)    |
| `mcp:patient-state`       | Query Patient State via the MCP Patient State server   |

See [API key scopes](https://olira.ai/api-docs) for the full list.

Pass the key to `OliraClient` or to `olira.init()`:

```python
import olira
olira.init(api_key="olira_prod_...")  # or set OLIRA_API_KEY env var
```

---

## Patient Management

Patients must exist before you can log events against them. Use the `api:manage-patients` scope.

Olira assigns a stable `id` to each patient at creation time. The `id` returned in the `Patient` object is what you use in all subsequent calls.

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")

# Create — Olira assigns the id; store it for future calls
patient = client.create_patient(
    first_name="Jane",
    last_name="Smith",
    timezone="America/New_York",
    primary_disease_site="breast",
    disease_stage="II",
)
patient_id = patient.id

# Get
patient = client.get_patient(patient_id=patient_id)

# List (paginated, returns PatientListResult)
result = client.list_patients(limit=50, offset=0)
for p in result.patients:
    print(p.id, p.first_name, p.last_name)

# Update (only supplied fields are changed)
patient = client.update_patient(patient_id=patient_id, disease_stage="III")

# Soft-delete
client.delete_patient(patient_id=patient_id)
```

---

## Logging

Log a single event in the background (fire-and-forget):

```python
import olira
from olira import OliraLogType

olira.init(api_key="olira_prod_...")

olira.log(
    log_type=OliraLogType.USER_LOGIN,
    patient_id=patient_id,  # id from patient.id
)
olira.flush()  # block until delivery
```

Send a batch directly and get back a result:

```python
from olira import OliraClient, LogSpec, OliraLogType, EsasItem

client = OliraClient(api_key="olira_prod_...")
result = client.log_batch([
    LogSpec(log_type=OliraLogType.USER_LOGIN, patient_id=patient_id),
    LogSpec(
        log_type=OliraLogType.SYMPTOM_REPORT,
        patient_id=patient_id,
        payload={
            "instrument": "esas_r",
            "symptoms": [EsasItem(name="pain", score=4).model_dump()],
        },
    ),
])
print(f"accepted={result.accepted}, failed={result.failed}")
client.close()
```

---

## Historical Ingestion

Backfill months or years of existing patient data. Requires the `sdk:historical-ingest` scope.

```python
import olira, time

# Submit a JSONL file — the SDK uploads it to S3 and creates the job
job = olira.create_ingestion_job(
    file="patients_and_logs.jsonl",
    idempotency_key="initial-onboarding-2026",
    require_confirmation=True,  # pause to review before replay
)

# Poll until awaiting confirmation (or complete)
while job.status not in ("completed", "failed", "awaiting_confirmation"):
    time.sleep(5)
    job = olira.get_ingestion_job(job_id=job.job_id)
    print(f"{job.stage}  {job.progress_pct:.1f}%")

# Review, then confirm to trigger graph replay and view backfill
print(f"Patients: {job.patients_processed}  Logs: {job.logs_processed}")
olira.confirm_ingestion_job(job_id=job.job_id)
```

See the [Backfilling historical data](https://olira.ai/api-docs) guide for the full walkthrough including inline payloads, validation, cancellation, and error recovery.

---

## Patient Token

Mint a short-lived JWT scoped to a single patient. Requires the `sdk:patient-token` scope.

Use this when a patient device needs to communicate with the [Olira MCP Patient State server](https://olira.ai/api-docs) — pass the token as a Bearer header. The token expires after 15 minutes and is locked to the specified patient.

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")
token = client.get_patient_token(patient_id=patient_id)

print(token.access_token)  # forward this to the patient device
print(token.expires_in)    # 900 (seconds)
client.close()
```

---

## Patient State

Read structured Patient State (modules, views, logs, and memories). Requires the `sdk:state-read` scope.

```python
from olira import OliraClient

client = OliraClient(api_key="olira_prod_...")

# Stable profile data (demographics, medications, care team, etc.)
stable = client.get_stable_data(patient_id=patient_id)

# Event-driven module (symptoms, labs, vitals, etc.)
module = client.get_event_state_module(patient_id=patient_id, module_type="symptoms")

# Generated view (template-driven summary your agents consume)
view = client.get_view(patient_id=patient_id, view_type="weekly_health_summary")

# Memories
memories = client.read_memories(patient_id=patient_id)
```

---

## Async client

All methods are available on `AsyncOliraClient` as coroutines:

```python
import asyncio
from olira import AsyncOliraClient, OliraLogType

async def main():
    async with AsyncOliraClient(api_key="olira_prod_...") as client:
        patient = await client.create_patient(
            first_name="Jane",
            last_name="Smith",
        )
        await client.log(
            log_type=OliraLogType.USER_LOGIN,
            patient_id=patient.id,
        )

asyncio.run(main())
```

---

## Error handling

```python
from olira import AuthError, ValidationError, RateLimitError, ServerError

try:
    client.log_batch([...])
except AuthError:
    # Invalid or revoked API key, or missing scope
    ...
except ValidationError:
    # Bad request (400/404/422) — e.g. unknown event type or missing required field
    ...
except RateLimitError as e:
    # Retry after e.retry_after seconds
    ...
except ServerError:
    # Transient server error after all retries exhausted
    ...
```

---

## Contributing

Dependencies are public PyPI packages only:

```bash
bash scripts/install-dev.sh
./scripts/pre-pr.sh
```
