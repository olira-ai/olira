"""Olira Python SDK — event ingestion client for the Olira Health platform."""

from typing import Any

from .client import AsyncOliraClient, OliraClient, OliraEnv
from .exceptions import (
    AuthError,
    NetworkError,
    OliraError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from .models import (
    BatchError,
    BatchResult,
    CreatePatientRequest,
    EsasItem,
    ExternalIdentifier,
    LabResultItem,
    LogSpec,
    OliraEventType,
    OliraTrace,
    Patient,
    PatientBatchItem,
    PatientBatchResult,
    PatientListResult,
    PatientToken,
    PerformingLab,
    TimePeriod,
    UpdatePatientRequest,
)
from .version import __version__

__all__ = [
    "__version__",
    "AsyncOliraClient",
    "OliraClient",
    "OliraEnv",
    "OliraError",
    "AuthError",
    "RateLimitError",
    "ValidationError",
    "ServerError",
    "NetworkError",
    # Event types and helpers
    "OliraEventType",
    "OliraTrace",
    "EsasItem",
    "LabResultItem",
    "PerformingLab",
    "TimePeriod",
    # Log types
    "LogSpec",
    "BatchResult",
    "BatchError",
    # Patient management types
    "ExternalIdentifier",
    "CreatePatientRequest",
    "UpdatePatientRequest",
    "Patient",
    "PatientBatchItem",
    "PatientBatchResult",
    "PatientListResult",
    "PatientToken",
    # Module-level log functions
    "init",
    "flush",
    "log",
    "log_batch",
    # Module-level patient functions
    "create_patient",
    "create_patients_batch",
    "get_patient",
    "list_patients",
    "update_patient",
    "delete_patient",
    "get_patient_token",
]

# Module-level singleton
_client: OliraClient | None = None


def init(
    api_key: str | None = None,
    *,
    environment: OliraEnv = OliraEnv.PRODUCTION,
    service_name: str | None = None,
    base_url: str = "https://api.prod.olira.ai",
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
    key = api_key or __import__("os").environ.get("OLIRA_API_KEY")
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
        raise OliraError("olira.init() must be called before logging events")
    return _client


def flush() -> None:
    """Block until all queued events are sent."""
    _get_client().flush()


def log(
    *,
    event_type: OliraEventType,
    patient_id: str,
    payload: dict[str, Any] | None = None,
    trace: OliraTrace | None = None,
    timestamp: str | None = None,
) -> None:
    """Enqueue an event for background delivery. Module-level proxy to the singleton client."""
    _get_client().log(
        event_type=event_type,
        patient_id=patient_id,
        payload=payload,
        trace=trace,
        timestamp=timestamp,
    )


def log_batch(events: list[LogSpec]) -> BatchResult:
    """Send a batch of events directly. Module-level proxy to the singleton client."""
    return _get_client().log_batch(events)


def create_patient(
    *,
    first_name: str,
    last_name: str,
    email: str | None = None,
    phone_number: str | None = None,
    date_of_birth: str | None = None,
    sex: str = "unknown",
    timezone: str,
    primary_disease_site: str | None = None,
    disease_stage: str | None = None,
    external_identifiers: list[ExternalIdentifier] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Patient:
    """Create a patient. Module-level proxy to the singleton client.

    Requires an API key with the api:manage-patients scope. Returns a :class:`Patient`
    with an Olira-assigned `id` — use it in all subsequent calls for this patient.
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
