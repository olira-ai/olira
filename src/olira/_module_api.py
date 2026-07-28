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
from .log_query import LogQuery
from .models import (
    BatchResult,
    Cohort,
    CohortDeleteResult,
    CohortListResult,
    CohortPatientMutationResult,
    CohortTemplateAssignment,
    CohortTemplatesResult,
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
    Project,
    ProjectListResult,
    SchemaActionResult,
    SchemaCheckResult,
    SchemaDetail,
    SchemaRegistrationResult,
    SchemaSummary,
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
    project: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    batch_size: int = 50,
    flush_interval: float = 1.5,
    max_queue_size: int = 10_000,
    timeout: float = 5.0,
    max_retries: int = 3,
    on_error: str = "drop",
    async_flush: bool = True,
) -> None:
    """Initialize the SDK. API key via OLIRA_API_KEY env var; project via OLIRA_PROJECT.

    ``project`` (id or slug) selects the workspace every call operates in. Omit it
    to use the key's own project (project-locked keys) or the org's default project.
    """
    global _client
    key = api_key or os.environ.get("OLIRA_API_KEY")
    if not key:
        raise OliraError("api_key is required; pass it to init() or set OLIRA_API_KEY")
    _client = OliraClient(
        api_key=key,
        environment=environment,
        service_name=service_name,
        project=project or os.environ.get("OLIRA_PROJECT"),
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
    write_back: bool = False,
    write_back_integration_id: str | None = None,
) -> None:
    """Enqueue a log for background delivery. Module-level proxy to the singleton client."""
    _get_client().log(
        log_type=log_type,
        patient_id=patient_id,
        payload=payload,
        trace=trace,
        timestamp=timestamp,
        metadata=metadata,
        write_back=write_back,
        write_back_integration_id=write_back_integration_id,
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


def delete_patient(*, patient_id: str, permanent: bool = False) -> None:
    """Delete a patient. Module-level proxy to the singleton client.

    Soft-deletes by default. Pass ``permanent=True`` to hard-delete the patient and
    cascade-delete all associated data (logs, state, conversations, etc). Irreversible —
    use to clean up a duplicate patient created before identifiers converged correctly.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().delete_patient(patient_id=patient_id, permanent=permanent)


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


def logs(patient_id: str) -> LogQuery:
    """Build a structured query over one patient's logs. Module-level proxy.

    Requires sdk:state-read scope.
    """
    return _get_client().logs(patient_id)


def population_logs(patient_ids: list[str] | None = None) -> LogQuery:
    """Build a structured query across the org (or a cohort). Module-level proxy.

    Requires sdk:state-read scope.
    """
    return _get_client().population_logs(patient_ids)


# ---------------------------------------------------------------------------
# Cohort management proxies (api:manage-patients scope)
# ---------------------------------------------------------------------------


def create_project(
    *,
    name: str,
    slug: str | None = None,
    description: str | None = None,
    environment: str | None = None,
) -> Project:
    """Create a project (isolated workspace). Module-level proxy to the singleton client.

    Requires api:manage-projects scope and an org-wide key. New projects start empty;
    pass the ``slug`` (the handle for ``init(project=...)``) or let it derive from ``name``.
    """
    return _get_client().create_project(name=name, slug=slug, description=description, environment=environment)


def list_projects() -> ProjectListResult:
    """List the organisation's projects. Module-level proxy to the singleton client."""
    return _get_client().list_projects()


def get_project(*, project: str) -> Project:
    """Get one project by id or slug. Module-level proxy to the singleton client."""
    return _get_client().get_project(project=project)


def duplicate_project(
    *,
    project: str,
    name: str,
    slug: str | None = None,
    description: str | None = None,
    environment: str | None = None,
) -> Project:
    """Duplicate a project's configuration into a new one. Module-level proxy.

    Copies config (platform config, pipelines, cohort definitions) — never
    patients, logs, or state. ``slug`` is the new project's handle (pass a
    distinct one; derived from ``name`` when omitted). Requires
    api:manage-projects scope + org-wide key.
    """
    return _get_client().duplicate_project(
        project=project, name=name, slug=slug, description=description, environment=environment
    )


def rename_project(
    *,
    project: str,
    name: str | None = None,
    description: str | None = None,
    environment: str | None = None,
) -> Project:
    """Rename a project or update its description/environment tag. Module-level proxy."""
    return _get_client().rename_project(project=project, name=name, description=description, environment=environment)


def deprecate_project(*, project: str) -> Project:
    """Soft-delete a project (deprecated list; data retained). Module-level proxy."""
    return _get_client().deprecate_project(project=project)


def restore_project(*, project: str) -> Project:
    """Reactivate a deprecated project, fully intact. Module-level proxy."""
    return _get_client().restore_project(project=project)


def delete_project(*, project: str) -> None:
    """Permanently delete a deprecated project (no recovery). Module-level proxy."""
    _get_client().delete_project(project=project)


def create_cohort(*, name: str, description: str | None = None) -> Cohort:
    """Create a named patient cohort. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope. Returns a :class:`Cohort`
    with an Olira-assigned ``id``. Names must be unique per organisation.
    """
    return _get_client().create_cohort(name=name, description=description)


def list_cohorts() -> CohortListResult:
    """List all cohorts in the organisation. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().list_cohorts()


def get_cohort(*, cohort_id: str) -> Cohort:
    """Get a cohort by id, including the full patient id list. Module-level proxy.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().get_cohort(cohort_id=cohort_id)


def update_cohort(
    *,
    cohort_id: str,
    name: str | None = None,
    description: str | None = None,
) -> Cohort:
    """Update a cohort's name or description. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope.
    Only supplied fields are changed; omitted fields are left as-is.
    """
    return _get_client().update_cohort(cohort_id=cohort_id, name=name, description=description)


def delete_cohort(*, cohort_id: str) -> CohortDeleteResult:
    """Permanently delete a cohort and all its template assignments. Module-level proxy.

    Requires an API key with the api:manage-patients scope. Patient records are not affected.
    """
    return _get_client().delete_cohort(cohort_id=cohort_id)


def add_patients_to_cohort(*, cohort_id: str, patient_ids: list[str]) -> CohortPatientMutationResult:
    """Add patients to a cohort (max 500 per call). Module-level proxy.

    Requires an API key with the api:manage-patients scope. Idempotent — patients already
    in the cohort are silently skipped.
    """
    return _get_client().add_patients_to_cohort(cohort_id=cohort_id, patient_ids=patient_ids)


def remove_patients_from_cohort(*, cohort_id: str, patient_ids: list[str]) -> CohortPatientMutationResult:
    """Remove patients from a cohort (max 500 per call). Module-level proxy.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().remove_patients_from_cohort(cohort_id=cohort_id, patient_ids=patient_ids)


def assign_cohort_template(*, cohort_id: str, summary_type: str) -> CohortTemplateAssignment:
    """Assign a summary type to a cohort. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope. Snapshot documents for
    existing cohort patients are seeded in the background.
    """
    return _get_client().assign_cohort_template(cohort_id=cohort_id, summary_type=summary_type)


def unassign_cohort_template(*, cohort_id: str, summary_type: str) -> dict[str, Any]:
    """Remove a summary type assignment from a cohort. Module-level proxy.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().unassign_cohort_template(cohort_id=cohort_id, summary_type=summary_type)


def list_cohort_templates(*, cohort_id: str) -> CohortTemplatesResult:
    """List all template assignments for a cohort. Module-level proxy.

    Requires an API key with the api:manage-patients scope.
    """
    return _get_client().list_cohort_templates(cohort_id=cohort_id)


# ---------------------------------------------------------------------------
# Org schema/mapping management proxies (api:org-config scope)
# ---------------------------------------------------------------------------


def register_schema(
    *,
    subtype: str,
    description: str = "",
    input_examples: list[dict[str, Any]] | None = None,
    schema: dict[str, Any] | None = None,
    mapping: dict[str, Any] | None = None,
) -> SchemaRegistrationResult:
    """Register a new org-native event subtype. Module-level proxy to the singleton client.

    Requires an API key with the api:org-config scope. Always lands as a pending
    request — Olira still reviews and materializes it before it can be activated.
    """
    return _get_client().register_schema(
        subtype=subtype,
        description=description,
        input_examples=input_examples,
        schema=schema,
        mapping=mapping,
    )


def list_schemas() -> list[SchemaSummary]:
    """List every org-native subtype you've registered. Module-level proxy.

    Requires an API key with the api:org-config scope.
    """
    return _get_client().list_schemas()


def get_schema(*, subtype: str) -> SchemaDetail:
    """Get a subtype's full version history. Module-level proxy.

    Requires an API key with the api:org-config scope.
    """
    return _get_client().get_schema(subtype=subtype)


def check_schema(
    *,
    examples: list[dict[str, Any]],
    subtype: str | None = None,
    version: int | None = None,
    schema: dict[str, Any] | None = None,
    mapping: dict[str, Any] | None = None,
) -> SchemaCheckResult:
    """Dry-run a schema/mapping over sample payloads — no writes. Module-level proxy.

    Requires an API key with the api:org-config scope.
    """
    return _get_client().check_schema(
        examples=examples, subtype=subtype, version=version, schema=schema, mapping=mapping
    )


def edit_schema(
    *,
    subtype: str,
    description: str | None = None,
    input_examples: list[dict[str, Any]] | None = None,
    schema: dict[str, Any] | None = None,
    mapping: dict[str, Any] | None = None,
) -> SchemaRegistrationResult:
    """Propose a schema/mapping change for a subtype you've already registered. Module-level proxy.

    Requires an API key with the api:org-config scope. Always opens a new pending
    request rather than mutating an active version in place.
    """
    return _get_client().edit_schema(
        subtype=subtype,
        description=description,
        input_examples=input_examples,
        schema=schema,
        mapping=mapping,
    )


def deprecate_schema(*, subtype: str, version: int | None = None) -> SchemaActionResult:
    """Deprecate a materialized version, or withdraw a still-pending request. Module-level proxy.

    Requires an API key with the api:org-config scope. Never a hard delete.
    """
    return _get_client().deprecate_schema(subtype=subtype, version=version)


def activate_schema_version(*, subtype: str, version: int) -> SchemaActionResult:
    """Activate an already-materialized version. Module-level proxy.

    Requires an API key with the api:org-config scope. Archives whichever version
    was previously active.
    """
    return _get_client().activate_schema_version(subtype=subtype, version=version)
