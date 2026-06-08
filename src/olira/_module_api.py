"""Module-level singleton client and convenience proxies.

``__init__`` re-exports these as the package-level ``olira.init()`` / ``olira.log()`` / … API.
The explicit :class:`OliraClient` / :class:`AsyncOliraClient` remain the
dependency-injectable path; this module is the optional convenience layer over a
process-wide singleton initialized by :func:`init`.
"""

import os
from typing import Any

from .client import DEFAULT_BASE_URL, OliraClient, OliraEnv
from .exceptions import OliraError
from .models import (
    BatchResult,
    CreatePatientRequest,
    EventsResult,
    EventStateModuleResult,
    EventStateModuleSummary,
    ExternalIdentifier,
    IngestionJob,
    IngestionJobListResult,
    IngestRecord,
    LogSpec,
    LogsResult,
    MemoriesResult,
    OliraLogType,
    OliraTrace,
    Patient,
    PatientBatchResult,
    PatientListResult,
    PatientToken,
    StableDataResult,
    ViewBlockResult,
    ViewBlocksListResult,
    ViewMeta,
    ViewRecentEventsResult,
    ViewResult,
)

_client: OliraClient | None = None


def init(
    api_key: str | None = None,
    *,
    environment: OliraEnv = OliraEnv.PRODUCTION,
    service_name: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    batch_size: int = 50,
    flush_interval: float = 1.5,
    max_queue_size: int = 10_000,
    timeout: float = 5.0,
    max_retries: int = 3,
    on_error: str = "drop",
    async_flush: bool = True,
) -> None:
    """Initialize the SDK. API key can be passed or set via OLIRA_API_KEY env var."""
    global _client
    key = api_key or os.environ.get("OLIRA_API_KEY")
    if not key:
        raise OliraError("api_key is required; pass it to init() or set OLIRA_API_KEY")
    _client = OliraClient(
        api_key=key,
        environment=environment,
        service_name=service_name,
        base_url=base_url,
        batch_size=batch_size,
        flush_interval=flush_interval,
        max_queue_size=max_queue_size,
        timeout=timeout,
        max_retries=max_retries,
        on_error=on_error,
        async_flush=async_flush,
    )


def _get_client() -> OliraClient:
    if _client is None:
        raise OliraError("olira.init() must be called before logging")
    return _client


def flush() -> None:
    """Block until all queued logs are sent."""
    _get_client().flush()


def log(
    *,
    log_type: OliraLogType,
    patient_id: str,
    payload: dict[str, Any] | None = None,
    trace: OliraTrace | None = None,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Enqueue a log for background delivery. Module-level proxy to the singleton client."""
    _get_client().log(
        log_type=log_type,
        patient_id=patient_id,
        payload=payload,
        trace=trace,
        timestamp=timestamp,
        metadata=metadata,
    )


def log_batch(events: list[LogSpec]) -> BatchResult:
    """Send a batch of logs directly. Module-level proxy to the singleton client."""
    return _get_client().log_batch(events)


def log_fhir(*, patient_id: str, resource: dict[str, Any]) -> BatchResult:
    """Submit a single FHIR R4 resource for immediate ingestion. Module-level proxy to the singleton client.

    Requires an API key with the sdk:event-log scope. Olira maps the resource to one or
    more platform log types via the FHIR absorber (same schema mapper used by Epic/Cerner
    integrations) and processes each event immediately. You do not choose log_type or
    build Olira-shaped payloads — the absorber handles the mapping.

    Raises ValidationError if the resource could not be mapped to any Olira events.
    """
    return _get_client().log_fhir(patient_id=patient_id, resource=resource)


def create_patient(
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
) -> Patient:
    """Create a patient. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope. Returns a :class:`Patient`
    with an Olira-assigned `id` — use it in all subsequent calls for this patient.
    Shell patients: pass at least one of ``external_identifiers``, ``email``,
    ``phone_number``, ``first_name``, ``last_name``, or ``date_of_birth``.
    """
    return _get_client().create_patient(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone_number,
        date_of_birth=date_of_birth,
        sex=sex,
        timezone=timezone,
        primary_disease_site=primary_disease_site,
        disease_stage=disease_stage,
        external_identifiers=external_identifiers,
        metadata=metadata,
    )


def create_patients_batch(patients: list[CreatePatientRequest]) -> PatientBatchResult:
    """Batch-create up to 500 patients. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope. Partial success is supported.
    Returns a :class:`PatientBatchResult` with items (successes) and errors (failures).
    """
    return _get_client().create_patients_batch(patients)


def get_patient(*, patient_id: str) -> Patient:
    """Get a patient by their id. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().get_patient(patient_id=patient_id)


def list_patients(
    *,
    limit: int = 100,
    offset: int = 0,
    external_system: str | None = None,
    external_value: str | None = None,
) -> PatientListResult:
    """List patients in your organisation. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().list_patients(
        limit=limit,
        offset=offset,
        external_system=external_system,
        external_value=external_value,
    )


def update_patient(
    *,
    patient_id: str,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone_number: str | None = None,
    sex: str | None = None,
    timezone: str | None = None,
    primary_disease_site: str | None = None,
    disease_stage: str | None = None,
    external_identifiers: list[ExternalIdentifier] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Patient:
    """Update a patient. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope.
    Only supplied fields are changed; omitted fields are left as-is.
    """
    return _get_client().update_patient(
        patient_id=patient_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone_number,
        sex=sex,
        timezone=timezone,
        primary_disease_site=primary_disease_site,
        disease_stage=disease_stage,
        external_identifiers=external_identifiers,
        metadata=metadata,
    )


def delete_patient(*, patient_id: str) -> None:
    """Soft-delete a patient. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().delete_patient(patient_id=patient_id)


def get_patient_token(*, patient_id: str) -> PatientToken:
    """Mint a short-lived patient-scoped JWT. Module-level proxy to the singleton client.

    Requires an API key with the sdk:patient-token scope.
    The returned JWT can be used as a Bearer token with the Olira MCP Patient State server.
    """
    return _get_client().get_patient_token(patient_id=patient_id)


def get_stable_data(*, patient_id: str, modules: list[str] | None = None) -> StableDataResult:
    """Get stable patient data. Module-level proxy to the singleton client.

    Requires sdk:state-read scope. Pass ``modules`` to fetch only specific modules:
    ``demographics``, ``condition_diagnosis``, ``medications``, ``user_preferences``.
    """
    return _get_client().get_stable_data(patient_id=patient_id, modules=modules)


def list_event_state_modules(*, patient_id: str) -> list[EventStateModuleSummary]:
    """List event state module types present for the patient. Module-level proxy to the singleton client.

    Requires sdk:state-read scope.
    """
    return _get_client().list_event_state_modules(patient_id=patient_id)


def get_event_state_module(*, patient_id: str, module_type: str) -> EventStateModuleResult:
    """Get a specific event state module by type. Module-level proxy to the singleton client.

    Requires sdk:state-read scope.
    """
    return _get_client().get_event_state_module(patient_id=patient_id, module_type=module_type)


def list_views(*, patient_id: str) -> list[ViewMeta]:
    """List available views for the patient. Module-level proxy to the singleton client.

    Requires sdk:state-read scope.
    """
    return _get_client().list_views(patient_id=patient_id)


def list_view_blocks(*, patient_id: str, view_type: str) -> ViewBlocksListResult:
    """List blocks within a specific view. Module-level proxy to the singleton client.

    Requires sdk:state-read scope.
    """
    return _get_client().list_view_blocks(patient_id=patient_id, view_type=view_type)


def get_view(*, patient_id: str, view_type: str) -> ViewResult:
    """Get a view snapshot. Module-level proxy to the singleton client.

    Requires sdk:state-read scope. Returns ``content["blocks"]`` (unified v2 model)
    plus ``content["temp"]`` when live entries are present.
    """
    return _get_client().get_view(patient_id=patient_id, view_type=view_type)


def get_view_block(*, patient_id: str, view_type: str, block_id: str) -> ViewBlockResult:
    """Get a specific block from a view. Module-level proxy to the singleton client.

    Requires sdk:state-read scope.
    """
    return _get_client().get_view_block(patient_id=patient_id, view_type=view_type, block_id=block_id)


def get_view_recent_events(*, patient_id: str, view_type: str, limit: int = 50) -> ViewRecentEventsResult:
    """Get recent TEMP events for a view type. Module-level proxy to the singleton client.

    Requires sdk:state-read scope.
    """
    return _get_client().get_view_recent_events(patient_id=patient_id, view_type=view_type, limit=limit)


def get_logs(
    *,
    patient_id: str,
    since: str | None = None,
    limit: int = 50,
    log_types: list[str] | None = None,
    trace_type: str | None = None,
    trace_id: str | None = None,
) -> LogsResult:
    """Get logs for the patient. Module-level proxy to the singleton client.

    Requires sdk:state-read scope.
    """
    return _get_client().get_logs(
        patient_id=patient_id,
        since=since,
        limit=limit,
        log_types=log_types,
        trace_type=trace_type,
        trace_id=trace_id,
    )


def get_events(
    *,
    patient_id: str,
    since: str | None = None,
    log_type: str | None = None,
    trace_type: str | None = None,
    trace_id: str | None = None,
    status: str = "complete",
    limit: int = 50,
) -> EventsResult:
    """Get events for the patient. Module-level proxy to the singleton client.

    Requires sdk:state-read scope.
    """
    return _get_client().get_events(
        patient_id=patient_id,
        since=since,
        log_type=log_type,
        trace_type=trace_type,
        trace_id=trace_id,
        status=status,
        limit=limit,
    )


def read_memories(*, patient_id: str, query: str | None = None, limit: int = 100) -> MemoriesResult:
    """Read memories for the patient. Module-level proxy to the singleton client.

    Requires sdk:state-read scope. Pass ``query`` for text search; omit to list all.
    """
    return _get_client().read_memories(patient_id=patient_id, query=query, limit=limit)


def create_ingestion_job(
    *,
    file: str | None = None,
    records: list[IngestRecord] | None = None,
    idempotency_key: str | None = None,
    require_confirmation: bool = True,
    rollback_on_cancel: bool = False,
    summary_types: list[str] | None = None,
    max_event_logs: int | None = None,
) -> IngestionJob:
    """Create a historical data ingestion job. Module-level proxy to the singleton client.

    Requires sdk:historical-ingest scope.
    Provide ``file`` (path to a JSONL file — SDK handles S3 upload) or ``records``
    (inline list of :class:`IngestRecord`, ≤ 50,000).
    """
    return _get_client().create_ingestion_job(
        file=file,
        records=records,
        idempotency_key=idempotency_key,
        require_confirmation=require_confirmation,
        rollback_on_cancel=rollback_on_cancel,
        summary_types=summary_types,
        max_event_logs=max_event_logs,
    )


def get_ingestion_job(*, job_id: str) -> IngestionJob:
    """Poll the status of a historical ingestion job. Module-level proxy.

    Requires sdk:historical-ingest scope.
    """
    return _get_client().get_ingestion_job(job_id=job_id)


def list_ingestion_jobs(
    *,
    idempotency_key: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> IngestionJobListResult:
    """List ingestion jobs for the org. Module-level proxy.

    Requires sdk:historical-ingest scope.
    """
    return _get_client().list_ingestion_jobs(
        idempotency_key=idempotency_key,
        page=page,
        page_size=page_size,
    )


def confirm_ingestion_job(*, job_id: str) -> IngestionJob:
    """Confirm a job in AWAITING_CONFIRMATION to start Phase 2. Module-level proxy.

    Requires sdk:historical-ingest scope.
    """
    return _get_client().confirm_ingestion_job(job_id=job_id)


def cancel_ingestion_job(*, job_id: str) -> IngestionJob:
    """Cancel an ingestion job. Module-level proxy.

    Requires sdk:historical-ingest scope.
    """
    return _get_client().cancel_ingestion_job(job_id=job_id)


def delete_ingestion_job_patient(*, job_id: str, patient_id: str) -> None:
    """Remove a patient during AWAITING_CONFIRMATION. Module-level proxy.

    Requires sdk:historical-ingest scope.
    """
    _get_client().delete_ingestion_job_patient(job_id=job_id, patient_id=patient_id)


def patch_ingestion_job(
    *,
    job_id: str,
    summary_types: list[str] | None = None,
) -> IngestionJob:
    """Update mutable fields while AWAITING_CONFIRMATION. Module-level proxy.

    Requires sdk:historical-ingest scope.
    """
    return _get_client().patch_ingestion_job(job_id=job_id, summary_types=summary_types)


def retry_view_backfill(*, job_id: str) -> IngestionJob:
    """Retry a failed view backfill on a COMPLETED_WITH_ERRORS job. Module-level proxy.

    Requires sdk:historical-ingest scope.
    """
    return _get_client().retry_view_backfill(job_id=job_id)
