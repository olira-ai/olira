"""Sync and async Olira clients."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx

from .documents import DocumentHandle, DocumentLogType, DocumentResource, upload_document_via_transport
from .exceptions import ValidationError
from .http import AsyncHttpTransport, HttpTransport
from .ingestion_confirm import confirm_ingestion_job_resilient, confirm_ingestion_job_resilient_async
from .log_query import AsyncLogQuery, LogQuery
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
    IngestDocument,
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
    UpdatePatientRequest,
    ViewBlockResult,
    ViewBlocksListResult,
    ViewMeta,
    ViewRecentEventsResult,
    ViewResult,
    _LogWire,
)
from .queue import BackgroundWorker
from .signals import SignalJob, SignalJobHandle, SignalSensorType, send_signals_via_transport
from .validation import validate_ingestion_file, validate_ingestion_records
from .version import __version__ as _sdk_version


class OliraEnv(StrEnum):
    """Environment for event routing. Use DEVELOPMENT for non-production systems."""

    PRODUCTION = "production"
    DEVELOPMENT = "development"


DEFAULT_BASE_URL = "https://app-api.prod.olira.ai/app-api"

_CONTENT_TYPE_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".gif": "image/gif",
}


def _guess_content_type(path: Path) -> str:
    return _CONTENT_TYPE_BY_SUFFIX.get(path.suffix.lower(), "application/pdf")


def _build_context(
    environment: OliraEnv,
    service_name: str | None,
    project: str | None = None,
) -> dict[str, str]:
    ctx = {
        "environment": environment.value,
        "service": service_name or "",
        "sdk_version": _sdk_version,
        "sdk_language": "python",
    }
    if project:
        ctx["project"] = project
    return ctx


class OliraClient:
    """
    Sync client for the Olira ingestion API. Use for multi-tenant or dependency injection.
    Module-level olira.init() creates a singleton; use OliraClient directly for multiple keys.
    """

    def __init__(
        self,
        *,
        api_key: str,
        environment: OliraEnv = OliraEnv.PRODUCTION,
        service_name: str | None = None,
        project: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        batch_size: int = 50,
        flush_interval: float = 1.5,
        max_queue_size: int = 10_000,
        timeout: float = 5.0,
        max_retries: int = 3,
        on_error: str | Callable[[Exception, list[str]], None] = "drop",
        async_flush: bool = True,
    ) -> None:
        self._api_key = api_key
        self._environment = environment
        self._service_name = service_name
        self._project = project
        self._base_url = base_url
        self._async_flush = async_flush
        self._context = _build_context(environment, service_name, project)

        self._transport = HttpTransport(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            project=project,
        )

        self._worker: BackgroundWorker | None = None
        if async_flush:
            self._worker = BackgroundWorker(
                send_batch=self._send_batch,
                batch_size=batch_size,
                flush_interval=flush_interval,
                max_queue_size=max_queue_size,
                on_error=on_error,
            )
            self._worker.start()

    def _send_batch(self, events: list[dict[str, Any]]) -> None:
        self._transport.send_batch(events)

    def _enqueue(self, event: _LogWire) -> bool:
        if self._worker is not None:
            return self._worker.enqueue(event)
        self._transport.send_batch([event.model_dump(mode="json")])
        return True

    def _emit(
        self,
        log_type: OliraLogType | str,
        patient_id: str,
        payload: dict[str, Any],
        trace: OliraTrace | None = None,
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
        write_back: bool = False,
        write_back_integration_id: str | None = None,
    ) -> None:
        event = _LogWire(
            log_type=str(log_type),
            patient_id=patient_id,
            payload=payload,
            metadata=metadata,
            context=self._context,
            trace=trace,
            timestamp=timestamp,
            write_back=write_back,
            write_back_integration_id=write_back_integration_id,
        )
        self._enqueue(event)

    def log(
        self,
        *,
        log_type: OliraLogType | str,
        patient_id: str,
        payload: dict[str, Any] | None = None,
        trace: OliraTrace | None = None,
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
        write_back: bool = False,
        write_back_integration_id: str | None = None,
    ) -> None:
        """Enqueue a log for background delivery. Returns immediately.

        ``write_back=True`` additionally requests that the log be written back
        into the org's connected EHR (requires the ``sdk:integration-write``
        scope and platform-side write configuration; silently ignored
        otherwise). With several write-configured integrations of the same
        type, ``write_back_integration_id`` names the target instance.
        """
        self._emit(
            log_type,
            patient_id,
            payload or {},
            trace=trace,
            timestamp=timestamp,
            metadata=metadata,
            write_back=write_back,
            write_back_integration_id=write_back_integration_id,
        )

    def log_fhir(self, *, patient_id: str, resource: dict[str, Any]) -> BatchResult:
        """Submit a single FHIR R4 resource for immediate ingestion. Requires sdk:event-log scope.

        Olira maps the resource to one or more platform log types via the FHIR absorber
        (same schema mapper used by Epic/Cerner integrations) and processes each event
        immediately for the patient. You do not choose log_type or build Olira-shaped
        payloads — the absorber handles the mapping.

        Raises ValidationError if the resource could not be mapped to any Olira events
        (unsupported type, unrecognized fields, or missing resourceType).
        """
        result = self._transport.log_fhir(patient_id, resource)
        if result.accepted == 0:
            msg = result.errors[0].message if result.errors else "FHIR resource produced no accepted events"
            raise ValidationError(msg)
        return result

    def log_batch(self, events: list[LogSpec]) -> BatchResult:
        """Send a batch of logs directly, bypassing the background queue.

        Sends a single /v1/logs/batch request and returns a BatchResult.
        """
        if not events:
            return BatchResult(accepted=0, failed=0)

        wire_events: list[dict[str, Any]] = []
        for spec in events:
            event = _LogWire(
                log_type=str(spec.log_type),
                patient_id=spec.patient_id,
                payload=spec.payload or {},
                metadata=spec.metadata,
                context=self._context,
                trace=spec.trace,
                timestamp=spec.timestamp,
                write_back=spec.write_back,
                write_back_integration_id=spec.write_back_integration_id,
                **({"idempotency_key": spec.idempotency_key} if spec.idempotency_key else {}),
            )
            wire_events.append(event.model_dump(mode="json", exclude_none=True))

        return self._transport.send_batch_direct(wire_events)

    def create_patient(
        self,
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
        """Create a patient. Requires api:manage-patients scope.

        Returns a :class:`Patient` with an Olira-assigned `id`. Use that `id` in all
        subsequent calls that reference this patient.

        Shell patients are supported: provide at least one of ``external_identifiers``,
        ``email``, ``phone_number``, ``first_name``, ``last_name``, or ``date_of_birth``.
        """
        req = CreatePatientRequest(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone_number=phone_number,
            date_of_birth=date_of_birth,
            sex=sex,
            timezone=timezone,
            primary_disease_site=primary_disease_site,
            disease_stage=disease_stage,
            external_identifiers=external_identifiers or [],
            metadata=metadata,
        )
        return self._transport.create_patient(req.model_dump(exclude_none=True))

    def create_patients_batch(self, patients: list[CreatePatientRequest]) -> PatientBatchResult:
        """Batch-create up to 500 patients. Requires api:manage-patients scope.

        Returns a PatientBatchResult with items (successes) and errors (failures).
        Partial success is supported — failures do not abort the rest of the batch.
        """
        wire = [p.model_dump(exclude_none=True) for p in patients]
        return self._transport.create_patients_batch(wire)

    def get_patient(self, *, patient_id: str) -> Patient:
        """Get a patient by their id. Requires api:manage-patients scope."""
        return self._transport.get_patient(patient_id)

    def list_patients(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        external_system: str | None = None,
        external_value: str | None = None,
    ) -> PatientListResult:
        """List patients in your organisation. Requires api:manage-patients scope."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if external_system is not None:
            params["external_system"] = external_system
        if external_value is not None:
            params["external_value"] = external_value
        return self._transport.list_patients(params)

    def update_patient(
        self,
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
        """Update a patient. Requires api:manage-patients scope.

        Only supplied fields are changed; omitted fields are left as-is.
        Pass ``external_identifiers=[]`` to clear all external identifiers.
        Pass ``metadata={}`` to clear metadata.
        """
        req = UpdatePatientRequest(
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
        return self._transport.update_patient(patient_id, req.model_dump(exclude_none=True))

    def delete_patient(self, *, patient_id: str, permanent: bool = False) -> None:
        """Delete a patient. Requires api:manage-patients scope.

        Soft-deletes by default. Pass ``permanent=True`` to hard-delete the patient and
        cascade-delete all associated data (logs, state, conversations, etc). Irreversible —
        use to clean up a duplicate patient created before identifiers converged correctly.
        """
        self._transport.delete_patient(patient_id, permanent=permanent)

    # ------------------------------------------------------------------
    # Cohort management (api:manage-patients scope)
    # ------------------------------------------------------------------

    def create_cohort(self, *, name: str, description: str | None = None) -> Cohort:
        """Create a named patient cohort. Requires api:manage-patients scope.

        Names must be unique per organisation. Returns a :class:`Cohort` with an
        Olira-assigned ``id`` — use it in all subsequent cohort calls.
        """
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        return self._transport.create_cohort(body)

    def create_project(
        self,
        *,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        environment: str | None = None,
    ) -> Project:
        """Create a project (isolated workspace). Requires api:manage-projects scope and an org-wide key.

        New projects start empty: fresh configuration, no patients or data carried
        over. ``slug`` is the handle you pass to ``init(project=...)`` /
        ``OliraClient(project=...)`` to operate in it — optional and normalized
        server-side (derived from ``name`` when omitted).
        """
        body: dict[str, Any] = {"name": name}
        if slug is not None:
            body["slug"] = slug
        if description is not None:
            body["description"] = description
        if environment is not None:
            body["environment"] = environment
        return self._transport.create_project(body)

    def list_projects(self) -> ProjectListResult:
        """List the organisation's projects. Requires api:manage-projects scope and an org-wide key."""
        return self._transport.list_projects()

    def get_project(self, *, project: str) -> Project:
        """Get one project by id or slug. Requires api:manage-projects scope and an org-wide key."""
        return self._transport.get_project(project)

    def duplicate_project(
        self,
        *,
        project: str,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        environment: str | None = None,
    ) -> Project:
        """Duplicate an existing project's configuration into a new one.

        Copies platform config, pipeline templates, and cohort definitions —
        never patients, logs, or state. ``project`` is the source id or slug;
        ``slug`` is the new project's handle (optional, normalized server-side;
        derived from ``name`` when omitted — pass a distinct one to avoid a
        collision with the source). Requires api:manage-projects scope and an
        org-wide key.
        """
        body: dict[str, Any] = {"name": name}
        if slug is not None:
            body["slug"] = slug
        if description is not None:
            body["description"] = description
        if environment is not None:
            body["environment"] = environment
        return self._transport.duplicate_project(project, body)

    def rename_project(
        self,
        *,
        project: str,
        name: str | None = None,
        description: str | None = None,
        environment: str | None = None,
    ) -> Project:
        """Rename a project or update its description/environment tag.

        ``project`` is the id or slug. Requires api:manage-projects scope and an
        org-wide key.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if environment is not None:
            body["environment"] = environment
        return self._transport.update_project(project, body)

    def deprecate_project(self, *, project: str) -> Project:
        """Soft-delete a project (moves it to the deprecated list; data retained).

        Cannot deprecate the default project or the org's last active project.
        Requires api:manage-projects scope and an org-wide key.
        """
        return self._transport.deprecate_project(project)

    def restore_project(self, *, project: str) -> Project:
        """Reactivate a deprecated project, fully intact.

        Requires api:manage-projects scope and an org-wide key.
        """
        return self._transport.restore_project(project)

    def delete_project(self, *, project: str) -> None:
        """Permanently delete a *deprecated* project and its config. No recovery.

        Blocked while the project still has patients (delete them first). Requires
        api:manage-projects scope and an org-wide key.
        """
        self._transport.delete_project(project)

    def list_cohorts(self) -> CohortListResult:
        """List all cohorts in the organisation. Requires api:manage-patients scope."""
        return self._transport.list_cohorts()

    def get_cohort(self, *, cohort_id: str) -> Cohort:
        """Get a cohort by id, including the full patient id list. Requires api:manage-patients scope."""
        return self._transport.get_cohort(cohort_id)

    def update_cohort(
        self,
        *,
        cohort_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> Cohort:
        """Update a cohort's name or description. Requires api:manage-patients scope.

        Only supplied fields are changed; omitted fields are left as-is.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        return self._transport.update_cohort(cohort_id, body)

    def delete_cohort(self, *, cohort_id: str) -> CohortDeleteResult:
        """Permanently delete a cohort and all its template assignments. Requires api:manage-patients scope.

        Patient records are not affected.
        """
        return self._transport.delete_cohort(cohort_id)

    def add_patients_to_cohort(self, *, cohort_id: str, patient_ids: list[str]) -> CohortPatientMutationResult:
        """Add patients to a cohort (max 500 per call). Requires api:manage-patients scope.

        Idempotent — patients already in the cohort are silently skipped.
        """
        return self._transport.add_patients_to_cohort(cohort_id, {"patient_ids": patient_ids})

    def remove_patients_from_cohort(self, *, cohort_id: str, patient_ids: list[str]) -> CohortPatientMutationResult:
        """Remove patients from a cohort (max 500 per call). Requires api:manage-patients scope."""
        return self._transport.remove_patients_from_cohort(cohort_id, {"patient_ids": patient_ids})

    def assign_cohort_template(self, *, cohort_id: str, summary_type: str) -> CohortTemplateAssignment:
        """Assign a summary type to a cohort. Requires api:manage-patients scope.

        Snapshot documents for existing cohort patients are seeded in the background.
        """
        return self._transport.assign_cohort_template(cohort_id, {"summary_type": summary_type})

    def unassign_cohort_template(self, *, cohort_id: str, summary_type: str) -> dict[str, Any]:
        """Remove a summary type assignment from a cohort. Requires api:manage-patients scope."""
        return self._transport.unassign_cohort_template(cohort_id, summary_type)

    def list_cohort_templates(self, *, cohort_id: str) -> CohortTemplatesResult:
        """List all template assignments for a cohort. Requires api:manage-patients scope."""
        return self._transport.list_cohort_templates(cohort_id)

    # ------------------------------------------------------------------
    # Org schema/mapping management (api:org-config scope)
    # ------------------------------------------------------------------

    def register_schema(
        self,
        *,
        subtype: str,
        description: str = "",
        input_examples: list[dict[str, Any]] | None = None,
        schema: dict[str, Any] | None = None,
        mapping: dict[str, Any] | None = None,
    ) -> SchemaRegistrationResult:
        """Register a new org-native event subtype. Requires api:org-config scope.

        Pass both ``schema`` and ``mapping`` for a "full_spec" submission (e.g. your own
        agent already authored them); pass neither/either for an "assisted" submission
        Olira will author from your ``input_examples`` + ``description``. Always lands
        as a pending request — Olira still reviews and materializes it before it can be
        activated (see :meth:`activate_schema_version`).
        """
        body: dict[str, Any] = {"subtype": subtype, "description": description}
        if input_examples is not None:
            body["input_examples"] = input_examples
        if schema is not None:
            body["payload_schema"] = schema
        if mapping is not None:
            body["mapping"] = mapping
        return self._transport.register_schema(body)

    def list_schemas(self) -> list[SchemaSummary]:
        """List every org-native subtype you've registered, with its aggregate status.

        Requires api:org-config scope.
        """
        return self._transport.list_schemas()

    def get_schema(self, *, subtype: str) -> SchemaDetail:
        """Get a subtype's full version history. Requires api:org-config scope."""
        return self._transport.get_schema(subtype)

    def check_schema(
        self,
        *,
        examples: list[dict[str, Any]],
        subtype: str | None = None,
        version: int | None = None,
        schema: dict[str, Any] | None = None,
        mapping: dict[str, Any] | None = None,
    ) -> SchemaCheckResult:
        """Dry-run a schema/mapping over sample payloads — no writes. Requires api:org-config scope.

        Pass ``subtype`` (optionally with ``version``) to check a stored or still-pending
        spec, or pass ``schema``/``mapping`` inline to check a candidate before registering
        it at all. Either inline value overrides the stored one for that field.
        """
        body: dict[str, Any] = {"examples": examples}
        if subtype is not None:
            body["subtype"] = subtype
        if version is not None:
            body["version"] = version
        if schema is not None:
            body["payload_schema"] = schema
        if mapping is not None:
            body["mapping"] = mapping
        return self._transport.check_schema(body)

    def edit_schema(
        self,
        *,
        subtype: str,
        description: str | None = None,
        input_examples: list[dict[str, Any]] | None = None,
        schema: dict[str, Any] | None = None,
        mapping: dict[str, Any] | None = None,
    ) -> SchemaRegistrationResult:
        """Propose a schema/mapping change for a subtype you've already registered.

        Requires api:org-config scope. Always opens a new pending request (never mutates
        an active version in place). Editing an already-active subtype defaults any
        field you omit to what's currently active, so the reviewer sees a complete
        proposed spec even from a partial edit.
        """
        body: dict[str, Any] = {}
        if description is not None:
            body["description"] = description
        if input_examples is not None:
            body["input_examples"] = input_examples
        if schema is not None:
            body["payload_schema"] = schema
        if mapping is not None:
            body["mapping"] = mapping
        return self._transport.edit_schema(subtype, body)

    def deprecate_schema(self, *, subtype: str, version: int | None = None) -> SchemaActionResult:
        """Deprecate a materialized version (default: the active one), or withdraw a
        still-pending request. Requires api:org-config scope. Never a hard delete.
        """
        params: dict[str, Any] = {}
        if version is not None:
            params["version"] = version
        return self._transport.deprecate_schema(subtype, params)

    def activate_schema_version(self, *, subtype: str, version: int) -> SchemaActionResult:
        """Activate an already-materialized version. Requires api:org-config scope.

        Archives whichever version was previously active.
        """
        return self._transport.activate_schema_version(subtype, version)

    def get_patient_token(self, *, patient_id: str) -> PatientToken:
        """Mint a short-lived patient-scoped JWT. Requires sdk:patient-token scope.

        The returned JWT can be passed to the Olira MCP Patient State server as a
        Bearer token.  It locks access to the specified patient for 15 minutes.
        """
        return self._transport.get_patient_token({"patient_id": patient_id})

    def get_stable_data(
        self,
        *,
        patient_id: str,
        modules: list[str] | None = None,
    ) -> StableDataResult:
        """Get stable patient data (demographics, condition, medications, preferences).

        Requires sdk:state-read scope. Pass ``modules`` to fetch only specific modules.
        """
        params: dict[str, Any] = {}
        if modules:
            params["modules"] = ",".join(modules)
        return self._transport.get_stable_data(patient_id, params)

    def list_event_state_modules(self, *, patient_id: str) -> list[EventStateModuleSummary]:
        """List event state module types present for the patient. Requires sdk:state-read scope."""
        raw = self._transport.list_event_state_modules(patient_id)
        return [EventStateModuleSummary.model_validate(m) for m in raw]

    def get_event_state_module(self, *, patient_id: str, module_type: str) -> EventStateModuleResult:
        """Get a specific event state module by type. Requires sdk:state-read scope."""
        return self._transport.get_event_state_module(patient_id, module_type)

    def list_views(self, *, patient_id: str) -> list[ViewMeta]:
        """List available views for the patient. Requires sdk:state-read scope."""
        raw = self._transport.list_views(patient_id)
        return [ViewMeta.model_validate(s) for s in raw]

    def list_view_blocks(self, *, patient_id: str, view_type: str) -> ViewBlocksListResult:
        """List blocks within a specific view. Requires sdk:state-read scope."""
        return self._transport.list_view_blocks(patient_id, view_type)

    def get_view(
        self,
        *,
        patient_id: str,
        view_type: str,
    ) -> ViewResult:
        """Get a view snapshot. Requires sdk:state-read scope.

        Returns the unified block list under ``content["blocks"]`` (v2 model),
        plus ``content["temp"]`` when live entries are present.
        """
        return self._transport.get_view(patient_id, view_type)

    def get_view_block(
        self,
        *,
        patient_id: str,
        view_type: str,
        block_id: str,
    ) -> ViewBlockResult:
        """Get a specific block from a view. Requires sdk:state-read scope."""
        return self._transport.get_view_block(patient_id, view_type, block_id)

    def get_view_recent_events(
        self,
        *,
        patient_id: str,
        view_type: str,
        limit: int = 50,
    ) -> ViewRecentEventsResult:
        """Get recent TEMP events for a view type. Requires sdk:state-read scope."""
        return self._transport.get_view_recent_events(patient_id, view_type, {"limit": limit})

    def get_logs(
        self,
        *,
        patient_id: str,
        since: str | None = None,
        limit: int = 50,
        log_types: list[str] | None = None,
        trace_type: str | None = None,
        trace_id: str | None = None,
    ) -> LogsResult:
        """Get logs for the patient. Requires sdk:state-read scope."""
        params: dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        if log_types:
            params["event_types"] = ",".join(log_types)
        if trace_type:
            params["trace_type"] = trace_type
        if trace_id:
            params["trace_id"] = trace_id
        return self._transport.get_logs(patient_id, params)

    def logs(self, patient_id: str) -> LogQuery:
        """Build a structured query over one patient's logs. Requires sdk:state-read."""
        return LogQuery(self._transport, patient_id=patient_id)

    def population_logs(self, patient_ids: list[str] | None = None) -> LogQuery:
        """Build a structured query across the org (or a cohort). Requires sdk:state-read."""
        return LogQuery(self._transport, patient_ids=patient_ids, population=True)

    def get_events(
        self,
        *,
        patient_id: str,
        since: str | None = None,
        log_type: str | None = None,
        trace_type: str | None = None,
        trace_id: str | None = None,
        status: str = "complete",
        limit: int = 50,
    ) -> EventsResult:
        """Get events for the patient. Requires sdk:state-read scope."""
        params: dict[str, Any] = {"status": status, "limit": limit}
        if since:
            params["since"] = since
        if log_type:
            params["log_type"] = log_type
        if trace_type:
            params["trace_type"] = trace_type
        if trace_id:
            params["trace_id"] = trace_id
        return self._transport.get_events(patient_id, params)

    def read_memories(
        self,
        *,
        patient_id: str,
        query: str | None = None,
        limit: int = 100,
    ) -> MemoriesResult:
        """Read memories for the patient. Requires sdk:state-read scope.

        Pass ``query`` for text-based search; omit to list all memories up to ``limit``.
        """
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        return self._transport.read_memories(patient_id, params)

    def create_ingestion_job(
        self,
        *,
        file: str | Path | None = None,
        records: list[IngestRecord] | None = None,
        documents: list[IngestDocument] | None = None,
        idempotency_key: str | None = None,
        require_confirmation: bool = True,
        summary_types: list[str] | None = None,
        max_event_logs: int | None = None,
    ) -> IngestionJob:
        """Create a historical data ingestion job. Requires sdk:historical-ingest scope.

        Provide either ``file`` (path to a JSONL file — SDK handles S3 upload),
        ``records`` (inline list of :class:`IngestRecord` objects, ≤ 50,000), and/or
        ``documents`` (document-package binaries — multi-PUT via ``jobs:begin``).

        When ``documents`` is set, the SDK builds a ``manifest.jsonl`` (records + document
        rows) and uploads via the package path.

        The job starts automatically. Poll with :meth:`get_ingestion_job` until
        ``status`` reaches ``awaiting_confirmation`` (default) or ``completed``.
        Pass ``require_confirmation=False`` to skip the review pause.

        Cancel (pre-Load) removes job-created patients with no other history; after Load
        has committed, cancel is a soft stop and leaves partial ontology in place.
        """
        if file is None and records is None and not documents:
            raise ValidationError("Provide 'file', 'records', and/or 'documents'")
        if file is not None and records is not None:
            raise ValidationError("Provide either 'file' or 'records', not both")
        if file is not None and documents:
            raise ValidationError("Document packages use records=… + documents=… (not file=)")

        body: dict[str, Any] = {
            "require_confirmation": require_confirmation,
        }
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        if summary_types is not None:
            body["summary_types"] = summary_types
        if max_event_logs is not None:
            body["max_event_logs"] = max_event_logs

        if documents:
            return self._create_document_package_job(body=body, records=records or [], documents=documents)

        if file is not None:
            try:
                sdk_cfg = self._transport.get_sdk_config()
                max_bytes: int = sdk_cfg.get("ingestion_max_file_bytes", 100 * 1024 * 1024)
            except Exception:
                max_bytes = 100 * 1024 * 1024
            url_data = self._transport.get_upload_url()
            all_issues = validate_ingestion_file(file, max_file_bytes=max_bytes)
            blocking = [e for e in all_issues if e.code != "patient_id_not_in_file"]
            if blocking:
                summary = "; ".join(f"line {e.line} [{e.code}] {e.message}" for e in blocking[:5])
                suffix = f" … and {len(blocking) - 5} more" if len(blocking) > 5 else ""
                raise ValidationError(f"JSONL validation failed ({len(blocking)} error(s)): {summary}{suffix}")
            with open(file, "rb") as fh:
                content = fh.read()
            httpx.put(url_data["upload_url"], content=content, timeout=120)
            body["s3_key"] = url_data["s3_key"]
        else:
            inline = records or []
            all_issues = validate_ingestion_records(inline)
            blocking = [e for e in all_issues if e.code != "patient_id_not_in_file"]
            if blocking:
                summary = "; ".join(f"record {e.line} [{e.code}] {e.message}" for e in blocking[:5])
                suffix = f" … and {len(blocking) - 5} more" if len(blocking) > 5 else ""
                raise ValidationError(f"Records validation failed ({len(blocking)} error(s)): {summary}{suffix}")
            body["records"] = [r.model_dump() for r in inline]

        return self._transport.create_ingestion_job(body)

    def _create_document_package_job(
        self,
        *,
        body: dict[str, Any],
        records: list[IngestRecord],
        documents: list[IngestDocument],
    ) -> IngestionJob:
        """jobs:begin → PUT documents → PUT manifest.jsonl → POST jobs."""

        for rec in records:
            if rec.type == "document":
                raise ValidationError("Pass document binaries via documents=, not IngestRecord.document in records")

        begin_docs: list[dict[str, Any]] = []
        resolved: list[tuple[IngestDocument, str, str, Path]] = []
        seen_ref_ids: set[str] = set()
        for i, doc in enumerate(documents):
            path = Path(doc.path)
            if not path.is_file():
                raise ValidationError(f"Document path not found: {doc.path}")
            ref_id = doc.ref_id or f"d{i + 1}"
            if ref_id in seen_ref_ids:
                raise ValidationError(f"Duplicate document ref_id: {ref_id!r}")
            seen_ref_ids.add(ref_id)
            content_type = doc.content_type or _guess_content_type(path)
            filename = doc.filename or path.name
            begin_docs.append(
                {
                    "ref_id": ref_id,
                    "content_type": content_type,
                    "filename": filename,
                    "size_bytes": path.stat().st_size,
                }
            )
            resolved.append((doc, ref_id, content_type, path))

        begin = self._transport.begin_ingestion_job({"documents": begin_docs})
        uploads_by_ref = {d["ref_id"]: d for d in begin["documents"]}

        for _doc, ref_id, content_type, path in resolved:
            upload = uploads_by_ref[ref_id]
            self._transport.put_presigned(
                upload["upload_url"],
                path.read_bytes(),
                headers={"Content-Type": content_type},
            )

        manifest_rows: list[IngestRecord] = list(records)
        for doc, ref_id, content_type, _path in resolved:
            upload = uploads_by_ref[ref_id]
            # Prefer relative key in the manifest (validate resolves under job prefix).
            rel_key = "/".join(str(upload["s3_key"]).split("/")[2:])
            # Patch content_type/filename onto a copy for the factory.
            patched = IngestDocument(
                path=doc.path,
                patient_id=doc.patient_id,
                log_type=doc.log_type,
                timestamp=doc.timestamp,
                ref_id=ref_id,
                document_type=doc.document_type,
                note_type=doc.note_type,
                source=doc.source,
                idempotency_key=doc.idempotency_key,
                content_type=content_type,
                filename=doc.filename or Path(doc.path).name,
            )
            manifest_rows.append(IngestRecord.document(patched, s3_key=rel_key, ref_id=ref_id))

        all_issues = validate_ingestion_records(manifest_rows)
        blocking = [e for e in all_issues if e.code != "patient_id_not_in_file"]
        if blocking:
            summary = "; ".join(f"record {e.line} [{e.code}] {e.message}" for e in blocking[:5])
            suffix = f" … and {len(blocking) - 5} more" if len(blocking) > 5 else ""
            raise ValidationError(f"Records validation failed ({len(blocking)} error(s)): {summary}{suffix}")

        manifest_bytes = ("\n".join(r.model_dump_json() for r in manifest_rows) + "\n").encode("utf-8")
        self._transport.put_presigned(begin["manifest_upload_url"], manifest_bytes)

        body["job_id"] = begin["job_id"]
        body["s3_key"] = begin["manifest_s3_key"]
        body["has_documents"] = True
        body["documents_total"] = len(documents)
        return self._transport.create_ingestion_job(body)

    def get_ingestion_job(self, *, job_id: str) -> IngestionJob:
        """Poll the status of an ingestion job. Requires sdk:historical-ingest scope."""
        return self._transport.get_ingestion_job(job_id)

    def list_ingestion_jobs(
        self,
        *,
        idempotency_key: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> IngestionJobListResult:
        """List ingestion jobs for the org. Requires sdk:historical-ingest scope."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if idempotency_key:
            params["idempotency_key"] = idempotency_key
        return self._transport.list_ingestion_jobs(params)

    def confirm_ingestion_job(
        self,
        *,
        job_id: str,
        initialize_missing_templates: bool = False,
        skip_backfill: bool = False,
    ) -> IngestionJob:
        """Confirm a job in AWAITING_CONFIRMATION to start Phase 2 (replay + backfill).

        Pass ``initialize_missing_templates=True`` to auto-initialize missing view
        slots on affected patients before backfill (recommended when
        ``job.missing_template_slots`` is non-empty).

        Pass ``skip_backfill=True`` to skip view generation entirely and complete
        the job after replay only.

        Requires sdk:historical-ingest scope.
        """
        return confirm_ingestion_job_resilient(
            skip_backfill=skip_backfill,
            patch_skip_backfill=lambda: self.patch_ingestion_job(job_id=job_id, skip_backfill=True),
            get_job=lambda: self.get_ingestion_job(job_id=job_id),
            confirm=lambda: self._transport.confirm_ingestion_job(
                job_id, initialize_missing_templates=initialize_missing_templates
            ),
        )

    def cancel_ingestion_job(self, *, job_id: str) -> IngestionJob:
        """Cancel an ingestion job. Requires sdk:historical-ingest scope.

        Allowed in AWAITING_CONFIRMATION (immediate cleanup) and REPLAYING / BACKFILLING
        (cooperative stop — already-replayed patients are not rolled back).
        """
        return self._transport.cancel_ingestion_job(job_id)

    def delete_ingestion_job_patient(self, *, job_id: str, patient_id: str) -> None:
        """Remove a patient and their STALE logs while the job is AWAITING_CONFIRMATION.

        Requires sdk:historical-ingest scope.
        """
        self._transport.delete_ingestion_job_patient(job_id, patient_id)

    def patch_ingestion_job(
        self,
        *,
        job_id: str,
        summary_types: list[str] | None = None,
        skip_backfill: bool | None = None,
    ) -> IngestionJob:
        """Update mutable fields while the job is AWAITING_CONFIRMATION.

        Requires sdk:historical-ingest scope. Currently supports updating ``summary_types``
        to control which views are backfilled in Phase 2, and ``skip_backfill`` to skip
        view generation in Phase 2.
        """
        body: dict[str, Any] = {}
        if summary_types is not None:
            body["summary_types"] = summary_types
        if skip_backfill is not None:
            body["skip_backfill"] = skip_backfill
        return self._transport.patch_ingestion_job(job_id, body)

    def retry_view_backfill(self, *, job_id: str) -> IngestionJob:
        """Retry a failed view backfill on a COMPLETED_WITH_ERRORS job.

        Requires sdk:historical-ingest scope. Patient and log data are intact —
        only view materialisation failed. Transitions the job back to BACKFILLING.
        """
        return self._transport.retry_view_backfill(job_id)

    def upload_document(
        self,
        *,
        patient_id: str,
        path: str | Path,
        log_type: DocumentLogType | str,
        timestamp: datetime,
        idempotency_key: str,
        document_type: str | None = None,
        note_type: str | None = None,
        source: Any | None = None,
        content_type: str | None = None,
        wait: bool = False,
        wait_timeout_s: float = 600.0,
    ) -> DocumentHandle:
        """Upload a PDF/image for OCR → EventLog (upload-url + PUT + commit).

        ``log_type`` is ``unstructured_report`` (requires ``document_type``) or
        ``clinical_note`` (requires ``note_type`` + ``source``). Types are chosen
        by the caller — the platform does not infer them from the file.
        """
        if not isinstance(timestamp, datetime):
            raise ValidationError("timestamp must be a datetime")
        handle = upload_document_via_transport(
            self._transport,
            patient_id=patient_id,
            path=path,
            log_type=log_type,
            timestamp=timestamp,
            idempotency_key=idempotency_key,
            document_type=document_type,
            note_type=note_type,
            source=source,
            content_type=content_type,
        )
        if wait:
            handle.wait(timeout_s=wait_timeout_s)
        return handle

    def get_document(self, document_id: str) -> DocumentResource:
        """Poll document OCR status (GET /v1/documents/{id})."""
        return self._transport.get_document(document_id)

    def send_signals(
        self,
        *,
        patient_id: str,
        sensor_type: "SignalSensorType | str",
        source_device: str,
        records: list[dict[str, Any]] | None = None,
        parquet: bytes | None = None,
        schema_version: str | None = None,
        sample_rate_hz: float | None = None,
        units: dict[str, str] | None = None,
        timestamp_unit: str | None = None,
        device_timezone: str | None = None,
    ) -> "SignalJobHandle":
        """Send a batch of passive sensor data (accelerometer / gyroscope / gps).

        Requires the sdk:event-log scope. Provide either ``records`` (list of dicts,
        each with a ``ts`` key plus the sensor's measurement fields — serialized to
        Parquet locally; requires ``pip install olira[signals]``) or ``parquet``
        (pre-serialized Parquet bytes).

        The SDK hashes the payload, stamps the schema version, measures the size, and
        routes automatically: small/medium payloads go through the synchronous door;
        large payloads upload via presigned S3 + manifest commit. Returns a
        :class:`~olira.signals.SignalJobHandle` — call ``handle.wait()`` to block until
        absorption finishes or ``handle.poll()`` for the current state.

        Optional collection metadata travels with the batch and is stored alongside the
        time-series data: ``sample_rate_hz`` (nominal device rate), ``units`` (per-field
        source units, converted server-side to canonical), ``timestamp_unit``
        ('s'/'ms'/'us' for epoch-encoded ts columns), ``device_timezone`` (IANA name,
        retains the original UTC offset).
        """
        return send_signals_via_transport(
            self._transport,
            patient_id=patient_id,
            sensor_type=sensor_type,
            source_device=source_device,
            records=records,
            parquet=parquet,
            schema_version=schema_version,
            sample_rate_hz=sample_rate_hz,
            units=units,
            timestamp_unit=timestamp_unit,
            device_timezone=device_timezone,
        )

    def get_signal_job(self, *, job_id: str) -> "SignalJob":
        """Poll a signal ingestion job. Requires sdk:event-log scope."""
        return self._transport.get_signal_job(job_id)

    def flush(self) -> None:
        """Block until all queued events are sent (or failed)."""
        if self._worker is not None:
            self._worker.flush()

    def close(self) -> None:
        """Stop the background worker and close the HTTP client."""
        if self._worker is not None:
            self._worker.close()
            self._worker = None
        self._transport.close()


class AsyncOliraClient:
    """
    Async client for the Olira ingestion API. Use async with for lifecycle.
    Same log() interface as OliraClient with async def signatures.
    """

    def __init__(
        self,
        *,
        api_key: str,
        environment: OliraEnv = OliraEnv.PRODUCTION,
        service_name: str | None = None,
        project: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        batch_size: int = 50,
        flush_interval: float = 1.5,
        max_queue_size: int = 10_000,
        timeout: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._environment = environment
        self._service_name = service_name
        self._project = project
        self._base_url = base_url
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_queue_size = max_queue_size
        self._timeout = timeout
        self._max_retries = max_retries
        self._context = _build_context(environment, service_name, project)
        self._transport: AsyncHttpTransport | None = None
        self._queue: asyncio.Queue[_LogWire | None] = asyncio.Queue(maxsize=max_queue_size)
        self._pending: list[_LogWire] = []
        self._lock = asyncio.Lock()
        self._worker_task: asyncio.Task[None] | None = None
        self._closed = False

    async def __aenter__(self) -> "AsyncOliraClient":
        self._transport = AsyncHttpTransport(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=self._timeout,
            max_retries=self._max_retries,
            project=self._project,
        )
        self._worker_task = asyncio.create_task(self._run_worker())
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def _run_worker(self) -> None:
        while not self._closed:
            try:
                item = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=self._flush_interval,
                )
            except TimeoutError:
                item = None
            if item is None:
                async with self._lock:
                    if self._pending:
                        await self._flush_pending_locked()
                continue
            async with self._lock:
                self._pending.append(item)
                if len(self._pending) >= self._batch_size:
                    await self._flush_pending_locked()
        async with self._lock:
            if self._pending:
                await self._flush_pending_locked()

    async def _flush_pending_locked(self) -> None:
        """Must be called with _lock held."""
        if not self._pending or not self._transport:
            return
        batch = self._pending[:]
        self._pending.clear()
        payloads = [e.model_dump(mode="json") for e in batch]
        await self._transport.send_batch(payloads)

    def _emit(
        self,
        log_type: OliraLogType | str,
        patient_id: str,
        payload: dict[str, Any],
        trace: OliraTrace | None = None,
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
        write_back: bool = False,
        write_back_integration_id: str | None = None,
    ) -> None:
        event = _LogWire(
            log_type=str(log_type),
            patient_id=patient_id,
            payload=payload,
            metadata=metadata,
            context=self._context,
            trace=trace,
            timestamp=timestamp,
            write_back=write_back,
            write_back_integration_id=write_back_integration_id,
        )
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def log(
        self,
        *,
        log_type: OliraLogType | str,
        patient_id: str,
        payload: dict[str, Any] | None = None,
        trace: OliraTrace | None = None,
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
        write_back: bool = False,
        write_back_integration_id: str | None = None,
    ) -> None:
        """Enqueue a log for background delivery.

        ``write_back=True`` additionally requests that the log be written back
        into the org's connected EHR (requires the ``sdk:integration-write``
        scope and platform-side write configuration; silently ignored
        otherwise). With several write-configured integrations of the same
        type, ``write_back_integration_id`` names the target instance.
        """
        self._emit(
            log_type,
            patient_id,
            payload or {},
            trace=trace,
            timestamp=timestamp,
            metadata=metadata,
            write_back=write_back,
            write_back_integration_id=write_back_integration_id,
        )

    async def log_fhir(self, *, patient_id: str, resource: dict[str, Any]) -> BatchResult:
        """Submit a single FHIR R4 resource for immediate ingestion. Requires sdk:event-log scope.

        Olira maps the resource to one or more platform log types via the FHIR absorber
        (same schema mapper used by Epic/Cerner integrations) and processes each event
        immediately for the patient. You do not choose log_type or build Olira-shaped
        payloads — the absorber handles the mapping.

        Raises ValidationError if the resource could not be mapped to any Olira events
        (unsupported type, unrecognized fields, or missing resourceType).
        """
        transport = self._require_transport("log_fhir")
        result = await transport.log_fhir(patient_id, resource)
        if result.accepted == 0:
            msg = result.errors[0].message if result.errors else "FHIR resource produced no accepted events"
            raise ValidationError(msg)
        return result

    async def log_batch(self, events: list[LogSpec]) -> BatchResult:
        """Send a batch of logs directly, bypassing the background queue.

        Sends a single /v1/logs/batch request and returns a BatchResult.
        """
        if not events:
            return BatchResult(accepted=0, failed=0)
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling log_batch()"
            )

        wire_events: list[dict[str, Any]] = []
        for spec in events:
            event = _LogWire(
                log_type=str(spec.log_type),
                patient_id=spec.patient_id,
                payload=spec.payload or {},
                metadata=spec.metadata,
                context=self._context,
                trace=spec.trace,
                timestamp=spec.timestamp,
                write_back=spec.write_back,
                write_back_integration_id=spec.write_back_integration_id,
                **({"idempotency_key": spec.idempotency_key} if spec.idempotency_key else {}),
            )
            wire_events.append(event.model_dump(mode="json", exclude_none=True))

        return await self._transport.send_batch_direct(wire_events)

    async def create_patient(
        self,
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
        """Create a patient. Requires api:manage-patients scope.

        Returns a :class:`Patient` with an Olira-assigned `id`. Use that `id` in all
        subsequent calls that reference this patient.

        Shell patients are supported: provide at least one of ``external_identifiers``,
        ``email``, ``phone_number``, ``first_name``, ``last_name``, or ``date_of_birth``.
        """
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling create_patient()"
            )
        req = CreatePatientRequest(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone_number=phone_number,
            date_of_birth=date_of_birth,
            sex=sex,
            timezone=timezone,
            primary_disease_site=primary_disease_site,
            disease_stage=disease_stage,
            external_identifiers=external_identifiers or [],
            metadata=metadata,
        )
        return await self._transport.create_patient(req.model_dump(exclude_none=True))

    async def create_patients_batch(self, patients: list[CreatePatientRequest]) -> PatientBatchResult:
        """Batch-create up to 500 patients. Requires api:manage-patients scope.

        Returns a PatientBatchResult with items (successes) and errors (failures).
        Partial success is supported — failures do not abort the rest of the batch.
        """
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling create_patients_batch()"
            )
        wire = [p.model_dump(exclude_none=True) for p in patients]
        return await self._transport.create_patients_batch(wire)

    async def get_patient(self, *, patient_id: str) -> Patient:
        """Get a patient by their id. Requires api:manage-patients scope."""
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling get_patient()"
            )
        return await self._transport.get_patient(patient_id)

    async def list_patients(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        external_system: str | None = None,
        external_value: str | None = None,
    ) -> PatientListResult:
        """List patients in your organisation. Requires api:manage-patients scope."""
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling list_patients()"
            )
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if external_system is not None:
            params["external_system"] = external_system
        if external_value is not None:
            params["external_value"] = external_value
        return await self._transport.list_patients(params)

    async def update_patient(
        self,
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
        """Update a patient. Requires api:manage-patients scope.

        Only supplied fields are changed; omitted fields are left as-is.
        Pass ``external_identifiers=[]`` to clear all external identifiers.
        Pass ``metadata={}`` to clear metadata.
        """
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling update_patient()"
            )
        req = UpdatePatientRequest(
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
        return await self._transport.update_patient(patient_id, req.model_dump(exclude_none=True))

    async def delete_patient(self, *, patient_id: str, permanent: bool = False) -> None:
        """Delete a patient. Requires api:manage-patients scope.

        Soft-deletes by default. Pass ``permanent=True`` to hard-delete the patient and
        cascade-delete all associated data (logs, state, conversations, etc). Irreversible —
        use to clean up a duplicate patient created before identifiers converged correctly.
        """
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling delete_patient()"
            )
        await self._transport.delete_patient(patient_id, permanent=permanent)

    # ------------------------------------------------------------------
    # Cohort management (api:manage-patients scope)
    # ------------------------------------------------------------------

    async def create_cohort(self, *, name: str, description: str | None = None) -> Cohort:
        """Create a named patient cohort. Requires api:manage-patients scope."""
        t = self._require_transport("create_cohort")
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        return await t.create_cohort(body)

    async def create_project(
        self,
        *,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        environment: str | None = None,
    ) -> Project:
        """Create a project (isolated workspace). Requires api:manage-projects scope and an org-wide key.

        New projects start empty: fresh configuration, no patients or data carried
        over. ``slug`` is the handle you pass to ``init(project=...)`` /
        ``OliraClient(project=...)`` to operate in it — optional and normalized
        server-side (derived from ``name`` when omitted).
        """
        body: dict[str, Any] = {"name": name}
        if slug is not None:
            body["slug"] = slug
        if description is not None:
            body["description"] = description
        if environment is not None:
            body["environment"] = environment
        return await self._require_transport("create_project").create_project(body)

    async def list_projects(self) -> ProjectListResult:
        """List the organisation's projects. Requires api:manage-projects scope and an org-wide key."""
        return await self._require_transport("list_projects").list_projects()

    async def get_project(self, *, project: str) -> Project:
        """Get one project by id or slug. Requires api:manage-projects scope and an org-wide key."""
        return await self._require_transport("get_project").get_project(project)

    async def duplicate_project(
        self,
        *,
        project: str,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        environment: str | None = None,
    ) -> Project:
        """Duplicate an existing project's configuration into a new one.

        Copies platform config, pipeline templates, and cohort definitions —
        never patients, logs, or state. ``project`` is the source id or slug;
        ``slug`` is the new project's handle (optional, normalized server-side;
        derived from ``name`` when omitted — pass a distinct one to avoid a
        collision with the source). Requires api:manage-projects scope and an
        org-wide key.
        """
        body: dict[str, Any] = {"name": name}
        if slug is not None:
            body["slug"] = slug
        if description is not None:
            body["description"] = description
        if environment is not None:
            body["environment"] = environment
        return await self._require_transport("duplicate_project").duplicate_project(project, body)

    async def rename_project(
        self,
        *,
        project: str,
        name: str | None = None,
        description: str | None = None,
        environment: str | None = None,
    ) -> Project:
        """Rename a project or update its description/environment tag.

        ``project`` is the id or slug. Requires api:manage-projects scope and an
        org-wide key.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if environment is not None:
            body["environment"] = environment
        return await self._require_transport("rename_project").update_project(project, body)

    async def deprecate_project(self, *, project: str) -> Project:
        """Soft-delete a project (moves it to the deprecated list; data retained).

        Cannot deprecate the default project or the org's last active project.
        Requires api:manage-projects scope and an org-wide key.
        """
        return await self._require_transport("deprecate_project").deprecate_project(project)

    async def restore_project(self, *, project: str) -> Project:
        """Reactivate a deprecated project, fully intact.

        Requires api:manage-projects scope and an org-wide key.
        """
        return await self._require_transport("restore_project").restore_project(project)

    async def delete_project(self, *, project: str) -> None:
        """Permanently delete a *deprecated* project and its config. No recovery.

        Blocked while the project still has patients (delete them first). Requires
        api:manage-projects scope and an org-wide key.
        """
        await self._require_transport("delete_project").delete_project(project)

    async def list_cohorts(self) -> CohortListResult:
        """List all cohorts in the organisation. Requires api:manage-patients scope."""
        return await self._require_transport("list_cohorts").list_cohorts()

    async def get_cohort(self, *, cohort_id: str) -> Cohort:
        """Get a cohort by id. Requires api:manage-patients scope."""
        return await self._require_transport("get_cohort").get_cohort(cohort_id)

    async def update_cohort(
        self,
        *,
        cohort_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> Cohort:
        """Update a cohort's name or description. Requires api:manage-patients scope."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        return await self._require_transport("update_cohort").update_cohort(cohort_id, body)

    async def delete_cohort(self, *, cohort_id: str) -> CohortDeleteResult:
        """Permanently delete a cohort and all its template assignments. Requires api:manage-patients scope."""
        return await self._require_transport("delete_cohort").delete_cohort(cohort_id)

    async def add_patients_to_cohort(self, *, cohort_id: str, patient_ids: list[str]) -> CohortPatientMutationResult:
        """Add patients to a cohort (max 500 per call). Requires api:manage-patients scope."""
        return await self._require_transport("add_patients_to_cohort").add_patients_to_cohort(
            cohort_id, {"patient_ids": patient_ids}
        )

    async def remove_patients_from_cohort(
        self, *, cohort_id: str, patient_ids: list[str]
    ) -> CohortPatientMutationResult:
        """Remove patients from a cohort (max 500 per call). Requires api:manage-patients scope."""
        return await self._require_transport("remove_patients_from_cohort").remove_patients_from_cohort(
            cohort_id, {"patient_ids": patient_ids}
        )

    async def assign_cohort_template(self, *, cohort_id: str, summary_type: str) -> CohortTemplateAssignment:
        """Assign a summary type to a cohort. Requires api:manage-patients scope."""
        return await self._require_transport("assign_cohort_template").assign_cohort_template(
            cohort_id, {"summary_type": summary_type}
        )

    async def unassign_cohort_template(self, *, cohort_id: str, summary_type: str) -> dict[str, Any]:
        """Remove a summary type assignment from a cohort. Requires api:manage-patients scope."""
        return await self._require_transport("unassign_cohort_template").unassign_cohort_template(
            cohort_id, summary_type
        )

    async def list_cohort_templates(self, *, cohort_id: str) -> CohortTemplatesResult:
        """List all template assignments for a cohort. Requires api:manage-patients scope."""
        return await self._require_transport("list_cohort_templates").list_cohort_templates(cohort_id)

    # ------------------------------------------------------------------
    # Org schema/mapping management (api:org-config scope)
    # ------------------------------------------------------------------

    async def register_schema(
        self,
        *,
        subtype: str,
        description: str = "",
        input_examples: list[dict[str, Any]] | None = None,
        schema: dict[str, Any] | None = None,
        mapping: dict[str, Any] | None = None,
    ) -> SchemaRegistrationResult:
        """Register a new org-native event subtype. Requires api:org-config scope.

        Pass both ``schema`` and ``mapping`` for a "full_spec" submission (e.g. your own
        agent already authored them); pass neither/either for an "assisted" submission
        Olira will author from your ``input_examples`` + ``description``. Always lands
        as a pending request — Olira still reviews and materializes it before it can be
        activated (see :meth:`activate_schema_version`).
        """
        body: dict[str, Any] = {"subtype": subtype, "description": description}
        if input_examples is not None:
            body["input_examples"] = input_examples
        if schema is not None:
            body["payload_schema"] = schema
        if mapping is not None:
            body["mapping"] = mapping
        return await self._require_transport("register_schema").register_schema(body)

    async def list_schemas(self) -> list[SchemaSummary]:
        """List every org-native subtype you've registered, with its aggregate status.

        Requires api:org-config scope.
        """
        return await self._require_transport("list_schemas").list_schemas()

    async def get_schema(self, *, subtype: str) -> SchemaDetail:
        """Get a subtype's full version history. Requires api:org-config scope."""
        return await self._require_transport("get_schema").get_schema(subtype)

    async def check_schema(
        self,
        *,
        examples: list[dict[str, Any]],
        subtype: str | None = None,
        version: int | None = None,
        schema: dict[str, Any] | None = None,
        mapping: dict[str, Any] | None = None,
    ) -> SchemaCheckResult:
        """Dry-run a schema/mapping over sample payloads — no writes. Requires api:org-config scope.

        Pass ``subtype`` (optionally with ``version``) to check a stored or still-pending
        spec, or pass ``schema``/``mapping`` inline to check a candidate before registering
        it at all. Either inline value overrides the stored one for that field.
        """
        body: dict[str, Any] = {"examples": examples}
        if subtype is not None:
            body["subtype"] = subtype
        if version is not None:
            body["version"] = version
        if schema is not None:
            body["payload_schema"] = schema
        if mapping is not None:
            body["mapping"] = mapping
        return await self._require_transport("check_schema").check_schema(body)

    async def edit_schema(
        self,
        *,
        subtype: str,
        description: str | None = None,
        input_examples: list[dict[str, Any]] | None = None,
        schema: dict[str, Any] | None = None,
        mapping: dict[str, Any] | None = None,
    ) -> SchemaRegistrationResult:
        """Propose a schema/mapping change for a subtype you've already registered.

        Requires api:org-config scope. Always opens a new pending request (never mutates
        an active version in place). Editing an already-active subtype defaults any
        field you omit to what's currently active, so the reviewer sees a complete
        proposed spec even from a partial edit.
        """
        body: dict[str, Any] = {}
        if description is not None:
            body["description"] = description
        if input_examples is not None:
            body["input_examples"] = input_examples
        if schema is not None:
            body["payload_schema"] = schema
        if mapping is not None:
            body["mapping"] = mapping
        return await self._require_transport("edit_schema").edit_schema(subtype, body)

    async def deprecate_schema(self, *, subtype: str, version: int | None = None) -> SchemaActionResult:
        """Deprecate a materialized version (default: the active one), or withdraw a
        still-pending request. Requires api:org-config scope. Never a hard delete.
        """
        params: dict[str, Any] = {}
        if version is not None:
            params["version"] = version
        return await self._require_transport("deprecate_schema").deprecate_schema(subtype, params)

    async def activate_schema_version(self, *, subtype: str, version: int) -> SchemaActionResult:
        """Activate an already-materialized version. Requires api:org-config scope.

        Archives whichever version was previously active.
        """
        return await self._require_transport("activate_schema_version").activate_schema_version(subtype, version)

    async def get_patient_token(self, *, patient_id: str) -> PatientToken:
        """Mint a short-lived patient-scoped JWT. Requires sdk:patient-token scope."""
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling get_patient_token()"
            )
        return await self._transport.get_patient_token({"patient_id": patient_id})

    def _require_transport(self, method: str) -> AsyncHttpTransport:
        if self._transport is None:
            raise ValidationError(
                f"AsyncOliraClient must be used as an async context manager before calling {method}()"
            )
        return self._transport

    async def get_stable_data(
        self,
        *,
        patient_id: str,
        modules: list[str] | None = None,
    ) -> StableDataResult:
        """Get stable patient data. Requires sdk:state-read scope."""
        transport = self._require_transport("get_stable_data")
        params: dict[str, Any] = {}
        if modules:
            params["modules"] = ",".join(modules)
        return await transport.get_stable_data(patient_id, params)

    async def list_event_state_modules(self, *, patient_id: str) -> list[EventStateModuleSummary]:
        """List event state module types present for the patient. Requires sdk:state-read scope."""
        transport = self._require_transport("list_event_state_modules")
        raw = await transport.list_event_state_modules(patient_id)
        return [EventStateModuleSummary.model_validate(m) for m in raw]

    async def get_event_state_module(self, *, patient_id: str, module_type: str) -> EventStateModuleResult:
        """Get a specific event state module by type. Requires sdk:state-read scope."""
        transport = self._require_transport("get_event_state_module")
        return await transport.get_event_state_module(patient_id, module_type)

    async def list_views(self, *, patient_id: str) -> list[ViewMeta]:
        """List available views for the patient. Requires sdk:state-read scope."""
        transport = self._require_transport("list_views")
        raw = await transport.list_views(patient_id)
        return [ViewMeta.model_validate(s) for s in raw]

    async def list_view_blocks(self, *, patient_id: str, view_type: str) -> ViewBlocksListResult:
        """List blocks within a specific view. Requires sdk:state-read scope."""
        transport = self._require_transport("list_view_blocks")
        return await transport.list_view_blocks(patient_id, view_type)

    async def get_view(
        self,
        *,
        patient_id: str,
        view_type: str,
    ) -> ViewResult:
        """Get a view snapshot. Requires sdk:state-read scope.

        Returns the unified block list under ``content["blocks"]`` (v2 model),
        plus ``content["temp"]`` when live entries are present.
        """
        transport = self._require_transport("get_view")
        return await transport.get_view(patient_id, view_type)

    async def get_view_block(
        self,
        *,
        patient_id: str,
        view_type: str,
        block_id: str,
    ) -> ViewBlockResult:
        """Get a specific block from a view. Requires sdk:state-read scope."""
        transport = self._require_transport("get_view_block")
        return await transport.get_view_block(patient_id, view_type, block_id)

    async def get_view_recent_events(
        self,
        *,
        patient_id: str,
        view_type: str,
        limit: int = 50,
    ) -> ViewRecentEventsResult:
        """Get recent TEMP events for a view type. Requires sdk:state-read scope."""
        transport = self._require_transport("get_view_recent_events")
        return await transport.get_view_recent_events(patient_id, view_type, {"limit": limit})

    async def get_logs(
        self,
        *,
        patient_id: str,
        since: str | None = None,
        limit: int = 50,
        log_types: list[str] | None = None,
        trace_type: str | None = None,
        trace_id: str | None = None,
    ) -> LogsResult:
        """Get logs for the patient. Requires sdk:state-read scope."""
        transport = self._require_transport("get_logs")
        params: dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        if log_types:
            params["event_types"] = ",".join(log_types)
        if trace_type:
            params["trace_type"] = trace_type
        if trace_id:
            params["trace_id"] = trace_id
        return await transport.get_logs(patient_id, params)

    def logs(self, patient_id: str) -> AsyncLogQuery:
        """Build a structured query over one patient's logs. Requires sdk:state-read."""
        transport = self._require_transport("logs")
        return AsyncLogQuery(transport, patient_id=patient_id)

    def population_logs(self, patient_ids: list[str] | None = None) -> AsyncLogQuery:
        """Build a structured query across the org (or a cohort). Requires sdk:state-read."""
        transport = self._require_transport("population_logs")
        return AsyncLogQuery(transport, patient_ids=patient_ids, population=True)

    async def get_events(
        self,
        *,
        patient_id: str,
        since: str | None = None,
        log_type: str | None = None,
        trace_type: str | None = None,
        trace_id: str | None = None,
        status: str = "complete",
        limit: int = 50,
    ) -> EventsResult:
        """Get events for the patient. Requires sdk:state-read scope."""
        transport = self._require_transport("get_events")
        params: dict[str, Any] = {"status": status, "limit": limit}
        if since:
            params["since"] = since
        if log_type:
            params["log_type"] = log_type
        if trace_type:
            params["trace_type"] = trace_type
        if trace_id:
            params["trace_id"] = trace_id
        return await transport.get_events(patient_id, params)

    async def read_memories(
        self,
        *,
        patient_id: str,
        query: str | None = None,
        limit: int = 100,
    ) -> MemoriesResult:
        """Read memories for the patient. Requires sdk:state-read scope."""
        transport = self._require_transport("read_memories")
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        return await transport.read_memories(patient_id, params)

    async def create_ingestion_job(
        self,
        *,
        file: str | Path | None = None,
        records: list[IngestRecord] | None = None,
        documents: list[IngestDocument] | None = None,
        idempotency_key: str | None = None,
        require_confirmation: bool = True,
        summary_types: list[str] | None = None,
        max_event_logs: int | None = None,
    ) -> IngestionJob:
        """Async version of create_ingestion_job. Requires sdk:historical-ingest scope."""
        if file is None and records is None and not documents:
            raise ValidationError("Provide 'file', 'records', and/or 'documents'")
        if file is not None and records is not None:
            raise ValidationError("Provide either 'file' or 'records', not both")
        if file is not None and documents:
            raise ValidationError("Document packages use records=… + documents=… (not file=)")

        transport = self._require_transport("create_ingestion_job")

        body: dict[str, Any] = {
            "require_confirmation": require_confirmation,
        }
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        if summary_types is not None:
            body["summary_types"] = summary_types
        if max_event_logs is not None:
            body["max_event_logs"] = max_event_logs

        if documents:
            return await self._create_document_package_job_async(
                transport, body=body, records=records or [], documents=documents
            )

        if file is not None:
            try:
                sdk_cfg = await transport.get_sdk_config()
                max_bytes: int = sdk_cfg.get("ingestion_max_file_bytes", 100 * 1024 * 1024)
            except Exception:
                max_bytes = 100 * 1024 * 1024
            url_data = await transport.get_upload_url()
            all_issues = validate_ingestion_file(file, max_file_bytes=max_bytes)
            blocking = [e for e in all_issues if e.code != "patient_id_not_in_file"]
            if blocking:
                summary = "; ".join(f"line {e.line} [{e.code}] {e.message}" for e in blocking[:5])
                suffix = f" … and {len(blocking) - 5} more" if len(blocking) > 5 else ""
                raise ValidationError(f"JSONL validation failed ({len(blocking)} error(s)): {summary}{suffix}")
            with open(file, "rb") as fh:
                content = fh.read()
            async with httpx.AsyncClient() as client:
                await client.put(url_data["upload_url"], content=content, timeout=120)
            body["s3_key"] = url_data["s3_key"]
        else:
            inline = records or []
            all_issues = validate_ingestion_records(inline)
            blocking = [e for e in all_issues if e.code != "patient_id_not_in_file"]
            if blocking:
                summary = "; ".join(f"record {e.line} [{e.code}] {e.message}" for e in blocking[:5])
                suffix = f" … and {len(blocking) - 5} more" if len(blocking) > 5 else ""
                raise ValidationError(f"Records validation failed ({len(blocking)} error(s)): {summary}{suffix}")
            body["records"] = [r.model_dump() for r in inline]

        return await transport.create_ingestion_job(body)

    async def _create_document_package_job_async(
        self,
        transport: AsyncHttpTransport,
        *,
        body: dict[str, Any],
        records: list[IngestRecord],
        documents: list[IngestDocument],
    ) -> IngestionJob:
        for rec in records:
            if rec.type == "document":
                raise ValidationError("Pass document binaries via documents=, not IngestRecord.document in records")

        begin_docs: list[dict[str, Any]] = []
        resolved: list[tuple[IngestDocument, str, str, Path]] = []
        seen_ref_ids: set[str] = set()
        for i, doc in enumerate(documents):
            path = Path(doc.path)
            if not path.is_file():
                raise ValidationError(f"Document path not found: {doc.path}")
            ref_id = doc.ref_id or f"d{i + 1}"
            if ref_id in seen_ref_ids:
                raise ValidationError(f"Duplicate document ref_id: {ref_id!r}")
            seen_ref_ids.add(ref_id)
            content_type = doc.content_type or _guess_content_type(path)
            filename = doc.filename or path.name
            begin_docs.append(
                {
                    "ref_id": ref_id,
                    "content_type": content_type,
                    "filename": filename,
                    "size_bytes": path.stat().st_size,
                }
            )
            resolved.append((doc, ref_id, content_type, path))

        begin = await transport.begin_ingestion_job({"documents": begin_docs})
        uploads_by_ref = {d["ref_id"]: d for d in begin["documents"]}

        for _doc, ref_id, content_type, path in resolved:
            upload = uploads_by_ref[ref_id]
            await transport.put_presigned(
                upload["upload_url"],
                path.read_bytes(),
                headers={"Content-Type": content_type},
            )

        manifest_rows: list[IngestRecord] = list(records)
        for doc, ref_id, content_type, _path in resolved:
            upload = uploads_by_ref[ref_id]
            rel_key = "/".join(str(upload["s3_key"]).split("/")[2:])
            patched = IngestDocument(
                path=doc.path,
                patient_id=doc.patient_id,
                log_type=doc.log_type,
                timestamp=doc.timestamp,
                ref_id=ref_id,
                document_type=doc.document_type,
                note_type=doc.note_type,
                source=doc.source,
                idempotency_key=doc.idempotency_key,
                content_type=content_type,
                filename=doc.filename or Path(doc.path).name,
            )
            manifest_rows.append(IngestRecord.document(patched, s3_key=rel_key, ref_id=ref_id))

        all_issues = validate_ingestion_records(manifest_rows)
        blocking = [e for e in all_issues if e.code != "patient_id_not_in_file"]
        if blocking:
            summary = "; ".join(f"record {e.line} [{e.code}] {e.message}" for e in blocking[:5])
            suffix = f" … and {len(blocking) - 5} more" if len(blocking) > 5 else ""
            raise ValidationError(f"Records validation failed ({len(blocking)} error(s)): {summary}{suffix}")

        manifest_bytes = ("\n".join(r.model_dump_json() for r in manifest_rows) + "\n").encode("utf-8")
        await transport.put_presigned(begin["manifest_upload_url"], manifest_bytes)

        body["job_id"] = begin["job_id"]
        body["s3_key"] = begin["manifest_s3_key"]
        body["has_documents"] = True
        body["documents_total"] = len(documents)
        return await transport.create_ingestion_job(body)

    async def get_ingestion_job(self, *, job_id: str) -> IngestionJob:
        """Async version of get_ingestion_job. Requires sdk:historical-ingest scope."""
        transport = self._require_transport("get_ingestion_job")
        return await transport.get_ingestion_job(job_id)

    async def list_ingestion_jobs(
        self,
        *,
        idempotency_key: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> IngestionJobListResult:
        """Async version of list_ingestion_jobs. Requires sdk:historical-ingest scope."""
        transport = self._require_transport("list_ingestion_jobs")
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if idempotency_key:
            params["idempotency_key"] = idempotency_key
        return await transport.list_ingestion_jobs(params)

    async def confirm_ingestion_job(
        self,
        *,
        job_id: str,
        initialize_missing_templates: bool = False,
        skip_backfill: bool = False,
    ) -> IngestionJob:
        """Async version of confirm_ingestion_job. Requires sdk:historical-ingest scope."""
        transport = self._require_transport("confirm_ingestion_job")
        return await confirm_ingestion_job_resilient_async(
            skip_backfill=skip_backfill,
            patch_skip_backfill=lambda: self.patch_ingestion_job(job_id=job_id, skip_backfill=True),
            get_job=lambda: self.get_ingestion_job(job_id=job_id),
            confirm=lambda: transport.confirm_ingestion_job(
                job_id, initialize_missing_templates=initialize_missing_templates
            ),
        )

    async def cancel_ingestion_job(self, *, job_id: str) -> IngestionJob:
        """Async version of cancel_ingestion_job. Requires sdk:historical-ingest scope."""
        transport = self._require_transport("cancel_ingestion_job")
        return await transport.cancel_ingestion_job(job_id)

    async def delete_ingestion_job_patient(self, *, job_id: str, patient_id: str) -> None:
        """Async version of delete_ingestion_job_patient. Requires sdk:historical-ingest scope."""
        transport = self._require_transport("delete_ingestion_job_patient")
        await transport.delete_ingestion_job_patient(job_id, patient_id)

    async def patch_ingestion_job(
        self,
        *,
        job_id: str,
        summary_types: list[str] | None = None,
        skip_backfill: bool | None = None,
    ) -> IngestionJob:
        """Async version of patch_ingestion_job. Requires sdk:historical-ingest scope."""
        transport = self._require_transport("patch_ingestion_job")
        body: dict[str, Any] = {}
        if summary_types is not None:
            body["summary_types"] = summary_types
        if skip_backfill is not None:
            body["skip_backfill"] = skip_backfill
        return await transport.patch_ingestion_job(job_id, body)

    async def retry_view_backfill(self, *, job_id: str) -> IngestionJob:
        """Async version of retry_view_backfill. Requires sdk:historical-ingest scope."""
        transport = self._require_transport("retry_view_backfill")
        return await transport.retry_view_backfill(job_id)

    async def flush(self) -> None:
        drained: list[_LogWire] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not None:
                drained.append(item)
        async with self._lock:
            self._pending.extend(drained)
            if self._pending and self._transport:
                await self._flush_pending_locked()

    async def aclose(self) -> None:
        self._closed = True
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        async with self._lock:
            if self._pending and self._transport:
                await self._flush_pending_locked()
        if self._transport is not None:
            await self._transport.aclose()
            self._transport = None
