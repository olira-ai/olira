"""HTTP transport for the ingestion API with retry policy. API keys are never logged."""

import asyncio
import logging
import time
from typing import Any, cast

import httpx

from .exceptions import AuthError, NetworkError, RateLimitError, ServerError, ValidationError
from .models import (
    BatchResult,
    Cohort,
    CohortDeleteResult,
    CohortListResult,
    CohortPatientMutationResult,
    CohortTemplateAssignment,
    CohortTemplatesResult,
    EventsResult,
    EventStateModuleResult,
    IngestionJob,
    IngestionJobListResult,
    LogQueryResult,
    LogsResult,
    MemoriesResult,
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
    ViewRecentEventsResult,
    ViewResult,
)

logger = logging.getLogger("olira")

REDACTED_KEY = "olira_***"


def _redact_key(api_key: str | None) -> str:
    if not api_key:
        return REDACTED_KEY
    return REDACTED_KEY


def _should_retry(status_code: int) -> bool:
    """True if we should retry: 408, 429, 5xx."""
    if status_code in (408, 429):
        return True
    if 500 <= status_code < 600:
        return True
    return False


def _parse_retry_after(response: httpx.Response) -> int:
    """Parse Retry-After header; return seconds (default 60)."""
    value = response.headers.get("Retry-After", "60")
    try:
        return int(value)
    except ValueError:
        return 60


def _parse_batch_result(body: dict[str, Any]) -> BatchResult:
    """Parse /v1/logs/batch response body into BatchResult."""
    return BatchResult.model_validate(body)


def _parse_patient(body: dict[str, Any]) -> Patient:
    """Parse a single patient response body into a Patient model."""
    return Patient.model_validate(body)


def _parse_patient_list_result(body: dict[str, Any]) -> PatientListResult:
    """Parse GET /v1/patients response into PatientListResult."""
    return PatientListResult.model_validate(body)


def _parse_patient_token(body: dict[str, Any]) -> PatientToken:
    """Parse POST /v1/auth/token response into PatientToken."""
    return PatientToken.model_validate(body)


class HttpTransport:
    """Sync HTTP transport: POST /v1/logs/batch with retry."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 5.0,
        max_retries: int = 3,
        project: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        headers = {"Authorization": f"Bearer {api_key}"}
        if project:
            # Selects the project (workspace) every request operates in; omitted =
            # the key's own project (locked keys) or the org's default project.
            headers["X-Olira-Project"] = project
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers=headers,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpTransport":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def send_batch(self, logs: list[dict[str, Any]]) -> dict[str, Any]:
        """Send a batch of logs (background worker path). Returns raw response dict."""
        return self._request("POST", "/v1/logs/batch", json={"logs": logs})  # type: ignore[no-any-return]

    def send_batch_direct(self, logs: list[dict[str, Any]]) -> BatchResult:
        """Send a batch directly (log_batch() path). Returns parsed BatchResult."""
        raw = self._request("POST", "/v1/logs/batch", json={"logs": logs})
        return _parse_batch_result(raw)

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_exception: Exception | None = None
        retry_after_seconds: int = 0

        for attempt in range(self._max_retries + 1):
            if retry_after_seconds > 0:
                time.sleep(retry_after_seconds)
            retry_after_seconds = 0

            try:
                response = self._client.request(method, path, json=json, params=params)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
                last_exception = NetworkError(str(e))
                if attempt < self._max_retries:
                    delay = min(2**attempt + (time.time() % 1), 60)
                    logger.debug(
                        "Request failed (attempt %s/%s), retry in %.1fs: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                        _redact_key(self._api_key),
                    )
                    time.sleep(delay)
                continue

            status = response.status_code

            if status in (401, 403):
                raise AuthError(f"API key rejected (HTTP {status}). Check key validity and scope.")

            if status == 409:
                response.read()
                raise ServerError(
                    f"Request rejected (HTTP {status}): {response.text[:500]}",
                    status_code=status,
                )

            if status in (400, 404, 422):
                response.read()
                raise ValidationError(f"Request rejected (HTTP {status}): {response.text[:500]}")

            if status == 429:
                retry_after_seconds = _parse_retry_after(response)
                if attempt == self._max_retries:
                    raise RateLimitError(
                        "Rate limited; retry after backoff",
                        retry_after=retry_after_seconds,
                    )
                logger.debug(
                    "Rate limited, retry after %ss (%s)",
                    retry_after_seconds,
                    _redact_key(self._api_key),
                )
                continue

            if _should_retry(status):
                if attempt == self._max_retries:
                    raise ServerError(f"Server error (HTTP {status}) after retries")
                delay = min(2**attempt + (time.time() % 1), 60)
                logger.debug(
                    "Server error %s (attempt %s/%s), retry in %.1fs",
                    status,
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                )
                time.sleep(delay)
                continue

            if 200 <= status < 300:
                return response.json() if response.content else {}

            response.read()
            last_exception = ServerError(f"Unexpected HTTP {status}")
            break

        if last_exception:
            raise last_exception
        return {}

    def create_patient(self, body: dict[str, Any]) -> Patient:
        """Create a patient (POST /v1/patients). Requires api:manage-patients scope."""
        raw = self._request("POST", "/v1/patients", json=body)
        return _parse_patient(raw)

    def get_patient(self, patient_id: str) -> Patient:
        """Get a patient by id (GET /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        raw = self._request("GET", f"/v1/patients/{patient_id}")
        return _parse_patient(raw)

    def list_patients(self, params: dict[str, Any]) -> PatientListResult:
        """List patients (GET /v1/patients). Requires api:manage-patients scope."""
        raw = self._request("GET", "/v1/patients", params=params)
        return _parse_patient_list_result(raw)

    def update_patient(self, patient_id: str, body: dict[str, Any]) -> Patient:
        """Update a patient (PUT /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        raw = self._request("PUT", f"/v1/patients/{patient_id}", json=body)
        return _parse_patient(raw)

    def delete_patient(self, patient_id: str) -> None:
        """Soft-delete a patient (DELETE /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        self._request("DELETE", f"/v1/patients/{patient_id}")

    def create_cohort(self, body: dict[str, Any]) -> Cohort:
        """Create a cohort (POST /v1/cohorts). Requires api:manage-patients scope."""
        raw = self._request("POST", "/v1/cohorts", json=body)
        return Cohort.model_validate(raw)

    def list_cohorts(self) -> CohortListResult:
        """List cohorts (GET /v1/cohorts). Requires api:manage-patients scope."""
        raw = self._request("GET", "/v1/cohorts")
        return CohortListResult.model_validate(raw)

    def create_project(self, body: dict[str, Any]) -> Project:
        """Create a project (POST /v1/projects). Requires api:manage-projects scope + org-wide key."""
        raw = self._request("POST", "/v1/projects", json=body)
        return Project.model_validate(raw)

    def list_projects(self) -> ProjectListResult:
        """List projects (GET /v1/projects). Requires api:manage-projects scope + org-wide key."""
        raw = self._request("GET", "/v1/projects")
        return ProjectListResult.model_validate(raw)

    def get_project(self, project: str) -> Project:
        """Get a project by id or slug (GET /v1/projects/{id_or_slug})."""
        raw = self._request("GET", f"/v1/projects/{project}")
        return Project.model_validate(raw)

    def duplicate_project(self, project: str, body: dict[str, Any]) -> Project:
        """Duplicate a project's config into a new one (POST /v1/projects/{id}/duplicate)."""
        raw = self._request("POST", f"/v1/projects/{project}/duplicate", json=body)
        return Project.model_validate(raw)

    def update_project(self, project: str, body: dict[str, Any]) -> Project:
        """Rename/retag a project (PATCH /v1/projects/{id})."""
        raw = self._request("PATCH", f"/v1/projects/{project}", json=body)
        return Project.model_validate(raw)

    def deprecate_project(self, project: str) -> Project:
        """Soft-delete a project (POST /v1/projects/{id}/deprecate)."""
        raw = self._request("POST", f"/v1/projects/{project}/deprecate")
        return Project.model_validate(raw)

    def restore_project(self, project: str) -> Project:
        """Reactivate a deprecated project (POST /v1/projects/{id}/restore)."""
        raw = self._request("POST", f"/v1/projects/{project}/restore")
        return Project.model_validate(raw)

    def delete_project(self, project: str) -> None:
        """Permanently delete a deprecated project (DELETE /v1/projects/{id}). No recovery."""
        self._request("DELETE", f"/v1/projects/{project}")

    def get_cohort(self, cohort_id: str) -> Cohort:
        """Get a cohort by id (GET /v1/cohorts/{cohort_id}). Requires api:manage-patients scope."""
        raw = self._request("GET", f"/v1/cohorts/{cohort_id}")
        return Cohort.model_validate(raw)

    def update_cohort(self, cohort_id: str, body: dict[str, Any]) -> Cohort:
        """Update a cohort (PUT /v1/cohorts/{cohort_id}). Requires api:manage-patients scope."""
        raw = self._request("PUT", f"/v1/cohorts/{cohort_id}", json=body)
        return Cohort.model_validate(raw)

    def delete_cohort(self, cohort_id: str) -> CohortDeleteResult:
        """Delete a cohort (DELETE /v1/cohorts/{cohort_id}). Requires api:manage-patients scope."""
        raw = self._request("DELETE", f"/v1/cohorts/{cohort_id}")
        return CohortDeleteResult.model_validate(raw)

    def add_patients_to_cohort(self, cohort_id: str, body: dict[str, Any]) -> CohortPatientMutationResult:
        """Add patients to a cohort (POST /v1/cohorts/{cohort_id}/patients). Requires api:manage-patients scope."""
        raw = self._request("POST", f"/v1/cohorts/{cohort_id}/patients", json=body)
        return CohortPatientMutationResult.model_validate(raw)

    def remove_patients_from_cohort(self, cohort_id: str, body: dict[str, Any]) -> CohortPatientMutationResult:
        """Remove patients from a cohort (DELETE /v1/cohorts/{cohort_id}/patients). Requires api:manage-patients scope."""
        raw = self._request("DELETE", f"/v1/cohorts/{cohort_id}/patients", json=body)
        return CohortPatientMutationResult.model_validate(raw)

    def assign_cohort_template(self, cohort_id: str, body: dict[str, Any]) -> CohortTemplateAssignment:
        """Assign a template to a cohort (POST /v1/cohorts/{cohort_id}/templates). Requires api:manage-patients scope."""
        raw = self._request("POST", f"/v1/cohorts/{cohort_id}/templates", json=body)
        return CohortTemplateAssignment.model_validate(raw)

    def unassign_cohort_template(self, cohort_id: str, summary_type: str) -> dict[str, Any]:
        """Unassign a template from a cohort (DELETE /v1/cohorts/{cohort_id}/templates/{summary_type}). Requires api:manage-patients scope."""
        raw: dict[str, Any] = self._request("DELETE", f"/v1/cohorts/{cohort_id}/templates/{summary_type}")
        return raw

    def list_cohort_templates(self, cohort_id: str) -> CohortTemplatesResult:
        """List templates assigned to a cohort (GET /v1/cohorts/{cohort_id}/templates). Requires api:manage-patients scope."""
        raw = self._request("GET", f"/v1/cohorts/{cohort_id}/templates")
        return CohortTemplatesResult.model_validate(raw)

    def register_schema(self, body: dict[str, Any]) -> SchemaRegistrationResult:
        """Register an org schema (POST /v1/schemas). Requires api:org-config scope."""
        raw = self._request("POST", "/v1/schemas", json=body)
        return SchemaRegistrationResult.model_validate(raw)

    def list_schemas(self) -> list[SchemaSummary]:
        """List org schemas (GET /v1/schemas). Requires api:org-config scope."""
        raw = self._request("GET", "/v1/schemas")
        return [SchemaSummary.model_validate(item) for item in raw]

    def get_schema(self, subtype: str) -> SchemaDetail:
        """Get one org schema's version history (GET /v1/schemas/{subtype}). Requires api:org-config scope."""
        raw = self._request("GET", f"/v1/schemas/{subtype}")
        return SchemaDetail.model_validate(raw)

    def check_schema(self, body: dict[str, Any]) -> SchemaCheckResult:
        """Dry-run a schema/mapping (POST /v1/schemas/check). Requires api:org-config scope."""
        raw = self._request("POST", "/v1/schemas/check", json=body)
        return SchemaCheckResult.model_validate(raw)

    def edit_schema(self, subtype: str, body: dict[str, Any]) -> SchemaRegistrationResult:
        """Propose a schema/mapping change (PATCH /v1/schemas/{subtype}). Requires api:org-config scope."""
        raw = self._request("PATCH", f"/v1/schemas/{subtype}", json=body)
        return SchemaRegistrationResult.model_validate(raw)

    def deprecate_schema(self, subtype: str, params: dict[str, Any]) -> SchemaActionResult:
        """Deprecate a version, or withdraw a pending request (DELETE /v1/schemas/{subtype}). Requires api:org-config scope."""
        raw = self._request("DELETE", f"/v1/schemas/{subtype}", params=params)
        return SchemaActionResult.model_validate(raw)

    def activate_schema_version(self, subtype: str, version: int) -> SchemaActionResult:
        """Activate a materialized version (POST /v1/schemas/{subtype}/versions/{version}/activate). Requires api:org-config scope."""
        raw = self._request("POST", f"/v1/schemas/{subtype}/versions/{version}/activate")
        return SchemaActionResult.model_validate(raw)

    def create_patients_batch(self, patients: list[dict[str, Any]]) -> PatientBatchResult:
        """Batch-create patients (POST /v1/patients/batch). Requires api:manage-patients scope."""
        raw = self._request("POST", "/v1/patients/batch", json={"patients": patients})
        return PatientBatchResult.model_validate(raw)

    def get_patient_token(self, body: dict[str, Any]) -> PatientToken:
        """Mint a patient-scoped JWT (POST /v1/auth/token). Requires sdk:patient-token scope."""
        raw = self._request("POST", "/v1/auth/token", json=body)
        return _parse_patient_token(raw)

    def get_stable_data(self, patient_id: str, params: dict[str, Any]) -> StableDataResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/stable", params=params)
        return StableDataResult.model_validate(raw)

    def list_event_state_modules(self, patient_id: str) -> list[Any]:
        raw = self._request("GET", f"/v1/state/{patient_id}/event-modules")
        return cast(list[Any], raw.get("modules", []))

    def get_event_state_module(self, patient_id: str, module_type: str) -> EventStateModuleResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/event-modules/{module_type}")
        return EventStateModuleResult.model_validate(raw)

    def list_views(self, patient_id: str) -> list[Any]:
        raw = self._request("GET", f"/v1/state/{patient_id}/views")
        return cast(list[Any], raw.get("views", []))

    def list_view_blocks(self, patient_id: str, view_type: str) -> ViewBlocksListResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/views/{view_type}/blocks")
        return ViewBlocksListResult.model_validate(raw)

    def get_view(self, patient_id: str, view_type: str) -> ViewResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/views/{view_type}")
        return ViewResult.model_validate(raw)

    def get_view_block(self, patient_id: str, view_type: str, block_id: str) -> ViewBlockResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/views/{view_type}/blocks/{block_id}")
        return ViewBlockResult.model_validate(raw)

    def get_view_recent_events(self, patient_id: str, view_type: str, params: dict[str, Any]) -> ViewRecentEventsResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/views/{view_type}/recent", params=params)
        return ViewRecentEventsResult.model_validate(raw)

    def get_logs(self, patient_id: str, params: dict[str, Any]) -> LogsResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/logs", params=params)
        return LogsResult.model_validate(raw)

    def query_logs(self, patient_id: str, body: dict[str, Any]) -> LogQueryResult:
        raw = self._request("POST", f"/v1/state/{patient_id}/logs/query", json=body)
        return LogQueryResult.model_validate(raw)

    def query_population_logs(self, body: dict[str, Any]) -> LogQueryResult:
        raw = self._request("POST", "/v1/state/logs/query", json=body)
        return LogQueryResult.model_validate(raw)

    def get_events(self, patient_id: str, params: dict[str, Any]) -> EventsResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/events", params=params)
        return EventsResult.model_validate(raw)

    def read_memories(self, patient_id: str, params: dict[str, Any]) -> MemoriesResult:
        raw = self._request("GET", f"/v1/state/{patient_id}/memories", params=params)
        return MemoriesResult.model_validate(raw)

    def get_sdk_config(self) -> dict[str, Any]:
        """Fetch the org's SDK configuration (GET /v1/sdk/config)."""
        return cast(dict[str, Any], self._request("GET", "/v1/sdk/config"))

    def get_upload_url(self) -> dict[str, Any]:
        """Get a presigned S3 PUT URL for file-based ingestion (POST /v1/ingestion/upload-url)."""
        return cast(dict[str, Any], self._request("POST", "/v1/ingestion/upload-url"))

    def create_ingestion_job(self, body: dict[str, Any]) -> IngestionJob:
        """Create a historical ingestion job (POST /v1/ingestion/jobs)."""
        raw = self._request("POST", "/v1/ingestion/jobs", json=body)
        return IngestionJob.model_validate(raw)

    def get_ingestion_job(self, job_id: str) -> IngestionJob:
        """Poll job status (GET /v1/ingestion/jobs/{job_id})."""
        raw = self._request("GET", f"/v1/ingestion/jobs/{job_id}")
        return IngestionJob.model_validate(raw)

    def list_ingestion_jobs(self, params: dict[str, Any]) -> IngestionJobListResult:
        """List ingestion jobs for the org (GET /v1/ingestion/jobs)."""
        raw = self._request("GET", "/v1/ingestion/jobs", params=params)
        return IngestionJobListResult.model_validate(raw)

    def confirm_ingestion_job(self, job_id: str, *, initialize_missing_templates: bool = False) -> IngestionJob:
        """Confirm a job in AWAITING_CONFIRMATION to trigger Phase 2 (POST /v1/ingestion/jobs/{job_id}/confirm)."""
        body: dict[str, Any] = {}
        if initialize_missing_templates:
            body["initialize_missing_templates"] = True
        raw = self._request("POST", f"/v1/ingestion/jobs/{job_id}/confirm", json=body or None)
        return IngestionJob.model_validate(raw)

    def cancel_ingestion_job(self, job_id: str) -> IngestionJob:
        """Cancel a job (POST /v1/ingestion/jobs/{job_id}/cancel)."""
        raw = self._request("POST", f"/v1/ingestion/jobs/{job_id}/cancel")
        return IngestionJob.model_validate(raw)

    def delete_ingestion_job_patient(self, job_id: str, patient_id: str) -> None:
        """Remove a patient during AWAITING_CONFIRMATION (DELETE /v1/ingestion/jobs/{job_id}/patients/{patient_id})."""
        self._request("DELETE", f"/v1/ingestion/jobs/{job_id}/patients/{patient_id}")

    def patch_ingestion_job(self, job_id: str, body: dict[str, Any]) -> IngestionJob:
        """Update mutable fields while AWAITING_CONFIRMATION (PATCH /v1/ingestion/jobs/{job_id})."""
        raw = self._request("PATCH", f"/v1/ingestion/jobs/{job_id}", json=body)
        return IngestionJob.model_validate(raw)

    def retry_view_backfill(self, job_id: str) -> IngestionJob:
        """Retry a failed ViewBackfillJob on a COMPLETED_WITH_ERRORS job (POST /v1/ingestion/jobs/{job_id}/retry-backfill)."""
        raw = self._request("POST", f"/v1/ingestion/jobs/{job_id}/retry-backfill")
        return IngestionJob.model_validate(raw)

    def log_fhir(self, patient_id: str, resource: dict[str, Any]) -> BatchResult:
        """Submit a single FHIR R4 resource (POST /v1/fhir/resource). Requires sdk:event-log scope."""
        raw = self._request("POST", "/v1/fhir/resource", json={"patient_id": patient_id, "resource": resource})
        return BatchResult.model_validate(raw)


class AsyncHttpTransport:
    """Async HTTP transport: POST /v1/logs/batch with retry."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 5.0,
        max_retries: int = 3,
        project: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        headers = {"Authorization": f"Bearer {api_key}"}
        if project:
            # Selects the project (workspace) every request operates in; omitted =
            # the key's own project (locked keys) or the org's default project.
            headers["X-Olira-Project"] = project
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_batch(self, logs: list[dict[str, Any]]) -> dict[str, Any]:
        """Send a batch of logs (background worker path). Returns raw response dict."""
        return await self._request("POST", "/v1/logs/batch", json={"logs": logs})  # type: ignore[no-any-return]

    async def send_batch_direct(self, logs: list[dict[str, Any]]) -> BatchResult:
        """Send a batch directly (log_batch() path). Returns parsed BatchResult."""
        raw = await self._request("POST", "/v1/logs/batch", json={"logs": logs})
        return _parse_batch_result(raw)

    async def create_patient(self, body: dict[str, Any]) -> Patient:
        """Create a patient (POST /v1/patients). Requires api:manage-patients scope."""
        raw = await self._request("POST", "/v1/patients", json=body)
        return _parse_patient(raw)

    async def get_patient(self, patient_id: str) -> Patient:
        """Get a patient by id (GET /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        raw = await self._request("GET", f"/v1/patients/{patient_id}")
        return _parse_patient(raw)

    async def list_patients(self, params: dict[str, Any]) -> PatientListResult:
        """List patients (GET /v1/patients). Requires api:manage-patients scope."""
        raw = await self._request("GET", "/v1/patients", params=params)
        return _parse_patient_list_result(raw)

    async def update_patient(self, patient_id: str, body: dict[str, Any]) -> Patient:
        """Update a patient (PUT /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        raw = await self._request("PUT", f"/v1/patients/{patient_id}", json=body)
        return _parse_patient(raw)

    async def delete_patient(self, patient_id: str) -> None:
        """Soft-delete a patient (DELETE /v1/patients/{patient_id}). Requires api:manage-patients scope."""
        await self._request("DELETE", f"/v1/patients/{patient_id}")

    async def create_cohort(self, body: dict[str, Any]) -> Cohort:
        """Create a cohort (POST /v1/cohorts). Requires api:manage-patients scope."""
        raw = await self._request("POST", "/v1/cohorts", json=body)
        return Cohort.model_validate(raw)

    async def list_cohorts(self) -> CohortListResult:
        """List cohorts (GET /v1/cohorts). Requires api:manage-patients scope."""
        raw = await self._request("GET", "/v1/cohorts")
        return CohortListResult.model_validate(raw)

    async def create_project(self, body: dict[str, Any]) -> Project:
        """Create a project (POST /v1/projects). Requires api:manage-projects scope + org-wide key."""
        raw = await self._request("POST", "/v1/projects", json=body)
        return Project.model_validate(raw)

    async def list_projects(self) -> ProjectListResult:
        """List projects (GET /v1/projects). Requires api:manage-projects scope + org-wide key."""
        raw = await self._request("GET", "/v1/projects")
        return ProjectListResult.model_validate(raw)

    async def get_project(self, project: str) -> Project:
        """Get a project by id or slug (GET /v1/projects/{id_or_slug})."""
        raw = await self._request("GET", f"/v1/projects/{project}")
        return Project.model_validate(raw)

    async def duplicate_project(self, project: str, body: dict[str, Any]) -> Project:
        """Duplicate a project's config into a new one (POST /v1/projects/{id}/duplicate)."""
        raw = await self._request("POST", f"/v1/projects/{project}/duplicate", json=body)
        return Project.model_validate(raw)

    async def update_project(self, project: str, body: dict[str, Any]) -> Project:
        """Rename/retag a project (PATCH /v1/projects/{id})."""
        raw = await self._request("PATCH", f"/v1/projects/{project}", json=body)
        return Project.model_validate(raw)

    async def deprecate_project(self, project: str) -> Project:
        """Soft-delete a project (POST /v1/projects/{id}/deprecate)."""
        raw = await self._request("POST", f"/v1/projects/{project}/deprecate")
        return Project.model_validate(raw)

    async def restore_project(self, project: str) -> Project:
        """Reactivate a deprecated project (POST /v1/projects/{id}/restore)."""
        raw = await self._request("POST", f"/v1/projects/{project}/restore")
        return Project.model_validate(raw)

    async def delete_project(self, project: str) -> None:
        """Permanently delete a deprecated project (DELETE /v1/projects/{id}). No recovery."""
        await self._request("DELETE", f"/v1/projects/{project}")

    async def get_cohort(self, cohort_id: str) -> Cohort:
        """Get a cohort by id (GET /v1/cohorts/{cohort_id}). Requires api:manage-patients scope."""
        raw = await self._request("GET", f"/v1/cohorts/{cohort_id}")
        return Cohort.model_validate(raw)

    async def update_cohort(self, cohort_id: str, body: dict[str, Any]) -> Cohort:
        """Update a cohort (PUT /v1/cohorts/{cohort_id}). Requires api:manage-patients scope."""
        raw = await self._request("PUT", f"/v1/cohorts/{cohort_id}", json=body)
        return Cohort.model_validate(raw)

    async def delete_cohort(self, cohort_id: str) -> CohortDeleteResult:
        """Delete a cohort (DELETE /v1/cohorts/{cohort_id}). Requires api:manage-patients scope."""
        raw = await self._request("DELETE", f"/v1/cohorts/{cohort_id}")
        return CohortDeleteResult.model_validate(raw)

    async def add_patients_to_cohort(self, cohort_id: str, body: dict[str, Any]) -> CohortPatientMutationResult:
        """Add patients to a cohort (POST /v1/cohorts/{cohort_id}/patients). Requires api:manage-patients scope."""
        raw = await self._request("POST", f"/v1/cohorts/{cohort_id}/patients", json=body)
        return CohortPatientMutationResult.model_validate(raw)

    async def remove_patients_from_cohort(self, cohort_id: str, body: dict[str, Any]) -> CohortPatientMutationResult:
        """Remove patients from a cohort (DELETE /v1/cohorts/{cohort_id}/patients). Requires api:manage-patients scope."""
        raw = await self._request("DELETE", f"/v1/cohorts/{cohort_id}/patients", json=body)
        return CohortPatientMutationResult.model_validate(raw)

    async def assign_cohort_template(self, cohort_id: str, body: dict[str, Any]) -> CohortTemplateAssignment:
        """Assign a template to a cohort (POST /v1/cohorts/{cohort_id}/templates). Requires api:manage-patients scope."""
        raw = await self._request("POST", f"/v1/cohorts/{cohort_id}/templates", json=body)
        return CohortTemplateAssignment.model_validate(raw)

    async def unassign_cohort_template(self, cohort_id: str, summary_type: str) -> dict[str, Any]:
        """Unassign a template from a cohort (DELETE /v1/cohorts/{cohort_id}/templates/{summary_type}). Requires api:manage-patients scope."""
        raw: dict[str, Any] = await self._request("DELETE", f"/v1/cohorts/{cohort_id}/templates/{summary_type}")
        return raw

    async def list_cohort_templates(self, cohort_id: str) -> CohortTemplatesResult:
        """List templates assigned to a cohort (GET /v1/cohorts/{cohort_id}/templates). Requires api:manage-patients scope."""
        raw = await self._request("GET", f"/v1/cohorts/{cohort_id}/templates")
        return CohortTemplatesResult.model_validate(raw)

    async def register_schema(self, body: dict[str, Any]) -> SchemaRegistrationResult:
        """Register an org schema (POST /v1/schemas). Requires api:org-config scope."""
        raw = await self._request("POST", "/v1/schemas", json=body)
        return SchemaRegistrationResult.model_validate(raw)

    async def list_schemas(self) -> list[SchemaSummary]:
        """List org schemas (GET /v1/schemas). Requires api:org-config scope."""
        raw = await self._request("GET", "/v1/schemas")
        return [SchemaSummary.model_validate(item) for item in raw]

    async def get_schema(self, subtype: str) -> SchemaDetail:
        """Get one org schema's version history (GET /v1/schemas/{subtype}). Requires api:org-config scope."""
        raw = await self._request("GET", f"/v1/schemas/{subtype}")
        return SchemaDetail.model_validate(raw)

    async def check_schema(self, body: dict[str, Any]) -> SchemaCheckResult:
        """Dry-run a schema/mapping (POST /v1/schemas/check). Requires api:org-config scope."""
        raw = await self._request("POST", "/v1/schemas/check", json=body)
        return SchemaCheckResult.model_validate(raw)

    async def edit_schema(self, subtype: str, body: dict[str, Any]) -> SchemaRegistrationResult:
        """Propose a schema/mapping change (PATCH /v1/schemas/{subtype}). Requires api:org-config scope."""
        raw = await self._request("PATCH", f"/v1/schemas/{subtype}", json=body)
        return SchemaRegistrationResult.model_validate(raw)

    async def deprecate_schema(self, subtype: str, params: dict[str, Any]) -> SchemaActionResult:
        """Deprecate a version, or withdraw a pending request (DELETE /v1/schemas/{subtype}). Requires api:org-config scope."""
        raw = await self._request("DELETE", f"/v1/schemas/{subtype}", params=params)
        return SchemaActionResult.model_validate(raw)

    async def activate_schema_version(self, subtype: str, version: int) -> SchemaActionResult:
        """Activate a materialized version (POST /v1/schemas/{subtype}/versions/{version}/activate). Requires api:org-config scope."""
        raw = await self._request("POST", f"/v1/schemas/{subtype}/versions/{version}/activate")
        return SchemaActionResult.model_validate(raw)

    async def create_patients_batch(self, patients: list[dict[str, Any]]) -> PatientBatchResult:
        """Batch-create patients (POST /v1/patients/batch). Requires api:manage-patients scope."""
        raw = await self._request("POST", "/v1/patients/batch", json={"patients": patients})
        return PatientBatchResult.model_validate(raw)

    async def get_patient_token(self, body: dict[str, Any]) -> PatientToken:
        """Mint a patient-scoped JWT (POST /v1/auth/token). Requires sdk:patient-token scope."""
        raw = await self._request("POST", "/v1/auth/token", json=body)
        return _parse_patient_token(raw)

    async def get_stable_data(self, patient_id: str, params: dict[str, Any]) -> StableDataResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/stable", params=params)
        return StableDataResult.model_validate(raw)

    async def list_event_state_modules(self, patient_id: str) -> list[Any]:
        raw = await self._request("GET", f"/v1/state/{patient_id}/event-modules")
        return cast(list[Any], raw.get("modules", []))

    async def get_event_state_module(self, patient_id: str, module_type: str) -> EventStateModuleResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/event-modules/{module_type}")
        return EventStateModuleResult.model_validate(raw)

    async def list_views(self, patient_id: str) -> list[Any]:
        raw = await self._request("GET", f"/v1/state/{patient_id}/views")
        return cast(list[Any], raw.get("views", []))

    async def list_view_blocks(self, patient_id: str, view_type: str) -> ViewBlocksListResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/views/{view_type}/blocks")
        return ViewBlocksListResult.model_validate(raw)

    async def get_view(self, patient_id: str, view_type: str) -> ViewResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/views/{view_type}")
        return ViewResult.model_validate(raw)

    async def get_view_block(self, patient_id: str, view_type: str, block_id: str) -> ViewBlockResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/views/{view_type}/blocks/{block_id}")
        return ViewBlockResult.model_validate(raw)

    async def get_view_recent_events(
        self, patient_id: str, view_type: str, params: dict[str, Any]
    ) -> ViewRecentEventsResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/views/{view_type}/recent", params=params)
        return ViewRecentEventsResult.model_validate(raw)

    async def get_logs(self, patient_id: str, params: dict[str, Any]) -> LogsResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/logs", params=params)
        return LogsResult.model_validate(raw)

    async def query_logs(self, patient_id: str, body: dict[str, Any]) -> LogQueryResult:
        raw = await self._request("POST", f"/v1/state/{patient_id}/logs/query", json=body)
        return LogQueryResult.model_validate(raw)

    async def query_population_logs(self, body: dict[str, Any]) -> LogQueryResult:
        raw = await self._request("POST", "/v1/state/logs/query", json=body)
        return LogQueryResult.model_validate(raw)

    async def get_events(self, patient_id: str, params: dict[str, Any]) -> EventsResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/events", params=params)
        return EventsResult.model_validate(raw)

    async def read_memories(self, patient_id: str, params: dict[str, Any]) -> MemoriesResult:
        raw = await self._request("GET", f"/v1/state/{patient_id}/memories", params=params)
        return MemoriesResult.model_validate(raw)

    async def get_sdk_config(self) -> dict[str, Any]:
        return cast(dict[str, Any], await self._request("GET", "/v1/sdk/config"))

    async def get_upload_url(self) -> dict[str, Any]:
        return cast(dict[str, Any], await self._request("POST", "/v1/ingestion/upload-url"))

    async def create_ingestion_job(self, body: dict[str, Any]) -> IngestionJob:
        raw = await self._request("POST", "/v1/ingestion/jobs", json=body)
        return IngestionJob.model_validate(raw)

    async def get_ingestion_job(self, job_id: str) -> IngestionJob:
        raw = await self._request("GET", f"/v1/ingestion/jobs/{job_id}")
        return IngestionJob.model_validate(raw)

    async def list_ingestion_jobs(self, params: dict[str, Any]) -> IngestionJobListResult:
        raw = await self._request("GET", "/v1/ingestion/jobs", params=params)
        return IngestionJobListResult.model_validate(raw)

    async def confirm_ingestion_job(self, job_id: str, *, initialize_missing_templates: bool = False) -> IngestionJob:
        body: dict[str, Any] = {}
        if initialize_missing_templates:
            body["initialize_missing_templates"] = True
        raw = await self._request("POST", f"/v1/ingestion/jobs/{job_id}/confirm", json=body or None)
        return IngestionJob.model_validate(raw)

    async def cancel_ingestion_job(self, job_id: str) -> IngestionJob:
        raw = await self._request("POST", f"/v1/ingestion/jobs/{job_id}/cancel")
        return IngestionJob.model_validate(raw)

    async def delete_ingestion_job_patient(self, job_id: str, patient_id: str) -> None:
        await self._request("DELETE", f"/v1/ingestion/jobs/{job_id}/patients/{patient_id}")

    async def patch_ingestion_job(self, job_id: str, body: dict[str, Any]) -> IngestionJob:
        raw = await self._request("PATCH", f"/v1/ingestion/jobs/{job_id}", json=body)
        return IngestionJob.model_validate(raw)

    async def retry_view_backfill(self, job_id: str) -> IngestionJob:
        raw = await self._request("POST", f"/v1/ingestion/jobs/{job_id}/retry-backfill")
        return IngestionJob.model_validate(raw)

    async def log_fhir(self, patient_id: str, resource: dict[str, Any]) -> BatchResult:
        """Submit a single FHIR R4 resource (POST /v1/fhir/resource). Requires sdk:event-log scope."""
        raw = await self._request("POST", "/v1/fhir/resource", json={"patient_id": patient_id, "resource": resource})
        return BatchResult.model_validate(raw)

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_exception: Exception | None = None
        retry_after_seconds: int = 0

        for attempt in range(self._max_retries + 1):
            if retry_after_seconds > 0:
                await asyncio.sleep(retry_after_seconds)
            retry_after_seconds = 0

            try:
                response = await self._client.request(method, path, json=json, params=params)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
                last_exception = NetworkError(str(e))
                if attempt < self._max_retries:
                    delay = min(2**attempt + (time.time() % 1), 60)
                    logger.debug(
                        "Request failed (attempt %s/%s), retry in %.1fs: %s",
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                        _redact_key(self._api_key),
                    )
                    await asyncio.sleep(delay)
                continue

            status = response.status_code

            if status in (401, 403):
                raise AuthError(f"API key rejected (HTTP {status}). Check key validity and scope.")

            if status == 409:
                await response.aread()
                raise ServerError(
                    f"Request rejected (HTTP {status}): {response.text[:500]}",
                    status_code=status,
                )

            if status in (400, 404, 422):
                await response.aread()
                raise ValidationError(f"Request rejected (HTTP {status}): {response.text[:500]}")

            if status == 429:
                retry_after_seconds = _parse_retry_after(response)
                if attempt == self._max_retries:
                    raise RateLimitError(
                        "Rate limited; retry after backoff",
                        retry_after=retry_after_seconds,
                    )
                logger.debug(
                    "Rate limited, retry after %ss (%s)",
                    retry_after_seconds,
                    _redact_key(self._api_key),
                )
                continue

            if _should_retry(status):
                if attempt == self._max_retries:
                    raise ServerError(f"Server error (HTTP {status}) after retries")
                delay = min(2**attempt + (time.time() % 1), 60)
                await asyncio.sleep(delay)
                continue

            if 200 <= status < 300:
                return response.json() if response.content else {}

            await response.aread()
            last_exception = ServerError(f"Unexpected HTTP {status}")
            break

        if last_exception:
            raise last_exception
        return {}
