"""Sync and async Olira clients."""

import asyncio
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from .exceptions import ValidationError
from .http import AsyncHttpTransport, HttpTransport
from .models import (
    BatchResult,
    CreatePatientRequest,
    EventLogsResult,
    EventStateModuleResult,
    EventStateModuleSummary,
    ExternalIdentifier,
    LogSpec,
    LogWire,
    MemoriesResult,
    OliraEventType,
    OliraTrace,
    Patient,
    PatientBatchResult,
    PatientListResult,
    PatientToken,
    StableDataResult,
    StateTransitionsResult,
    SummaryBlockResult,
    SummaryBlocksListResult,
    SummaryMeta,
    SummaryRecentEventsResult,
    SummaryResult,
    UpdatePatientRequest,
)
from .queue import BackgroundWorker
from .version import __version__ as _sdk_version


class OliraEnv(StrEnum):
    """Environment for event routing. Use DEVELOPMENT for non-production systems."""

    PRODUCTION = "production"
    DEVELOPMENT = "development"


DEFAULT_BASE_URL = "https://api.prod.olira.ai"


def _build_context(
    environment: OliraEnv,
    service_name: str | None,
) -> dict[str, str]:
    return {
        "environment": environment.value,
        "service": service_name or "",
        "sdk_version": _sdk_version,
        "sdk_language": "python",
    }


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
        self._base_url = base_url
        self._async_flush = async_flush
        self._context = _build_context(environment, service_name)

        self._transport = HttpTransport(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
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

    def _enqueue(self, event: LogWire) -> bool:
        if self._worker is not None:
            return self._worker.enqueue(event)
        # Sync mode: send immediately via batch endpoint
        self._transport.send_batch([event.model_dump(mode="json")])
        return True

    def _emit(
        self,
        event_type: OliraEventType,
        patient_id: str,
        payload: dict[str, Any],
        trace: OliraTrace | None = None,
        timestamp: str | None = None,
    ) -> None:
        event = LogWire(
            event_name=event_type.value,
            patient_id=patient_id,
            payload=payload,
            context=self._context,
            trace=trace,
            timestamp=timestamp,
        )
        self._enqueue(event)

    def log(
        self,
        *,
        event_type: OliraEventType,
        patient_id: str,
        payload: dict[str, Any] | None = None,
        trace: OliraTrace | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Enqueue an event for background delivery. Returns immediately."""
        self._emit(event_type, patient_id, payload or {}, trace=trace, timestamp=timestamp)

    def log_batch(self, events: list[LogSpec]) -> BatchResult:
        """Send a batch of logs directly, bypassing the background queue.

        Sends a single /v1/logs/batch request and returns a BatchResult.
        """
        if not events:
            return BatchResult(accepted=0, failed=0)

        wire_events: list[dict[str, Any]] = []
        for spec in events:
            event = LogWire(
                event_name=spec.event_type.value,
                patient_id=spec.patient_id,
                payload=spec.payload or {},
                context=self._context,
                trace=spec.trace,
                timestamp=spec.timestamp,
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

    def delete_patient(self, *, patient_id: str) -> None:
        """Soft-delete a patient. Requires api:manage-patients scope."""
        self._transport.delete_patient(patient_id)

    def get_patient_token(self, *, patient_id: str) -> PatientToken:
        """Mint a short-lived patient-scoped JWT. Requires sdk:patient-token scope.

        The returned JWT can be passed to the Olira MCP Patient State server as a
        Bearer token.  It locks access to the specified patient for 15 minutes.
        """
        return self._transport.get_patient_token({"patient_id": patient_id})

    # --- State-read methods (sdk:state-read scope) ---

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

    def list_summaries(self, *, patient_id: str) -> list[SummaryMeta]:
        """List available summaries for the patient. Requires sdk:state-read scope."""
        raw = self._transport.list_summaries(patient_id)
        return [SummaryMeta.model_validate(s) for s in raw]

    def list_summary_blocks(self, *, patient_id: str, summary_type: str) -> SummaryBlocksListResult:
        """List blocks within a specific summary. Requires sdk:state-read scope."""
        return self._transport.list_summary_blocks(patient_id, summary_type)

    def get_summary(
        self,
        *,
        patient_id: str,
        summary_type: str,
    ) -> SummaryResult:
        """Get a summary snapshot. Requires sdk:state-read scope.

        Returns the unified block list under ``content["blocks"]`` (v2 model),
        plus ``content["temp"]`` when live entries are present.
        """
        return self._transport.get_summary(patient_id, summary_type)

    def get_summary_block(
        self,
        *,
        patient_id: str,
        summary_type: str,
        block_id: str,
    ) -> SummaryBlockResult:
        """Get a specific block from a summary. Requires sdk:state-read scope."""
        return self._transport.get_summary_block(patient_id, summary_type, block_id)

    def get_summary_recent_events(
        self,
        *,
        patient_id: str,
        summary_type: str,
        limit: int = 50,
    ) -> SummaryRecentEventsResult:
        """Get recent TEMP events for a summary type. Requires sdk:state-read scope."""
        return self._transport.get_summary_recent_events(patient_id, summary_type, {"limit": limit})

    def get_event_logs(
        self,
        *,
        patient_id: str,
        since: str | None = None,
        limit: int = 50,
        event_types: list[str] | None = None,
        trace_type: str | None = None,
        trace_id: str | None = None,
    ) -> EventLogsResult:
        """Get event logs for the patient. Requires sdk:state-read scope."""
        params: dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        if event_types:
            params["event_types"] = ",".join(event_types)
        if trace_type:
            params["trace_type"] = trace_type
        if trace_id:
            params["trace_id"] = trace_id
        return self._transport.get_event_logs(patient_id, params)

    def get_state_transitions(
        self,
        *,
        patient_id: str,
        since: str | None = None,
        event_log_type: str | None = None,
        trace_type: str | None = None,
        trace_id: str | None = None,
        status: str = "complete",
        limit: int = 50,
    ) -> StateTransitionsResult:
        """Get state transitions for the patient. Requires sdk:state-read scope."""
        params: dict[str, Any] = {"status": status, "limit": limit}
        if since:
            params["since"] = since
        if event_log_type:
            params["event_log_type"] = event_log_type
        if trace_type:
            params["trace_type"] = trace_type
        if trace_id:
            params["trace_id"] = trace_id
        return self._transport.get_state_transitions(patient_id, params)

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
        self._base_url = base_url
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_queue_size = max_queue_size
        self._timeout = timeout
        self._max_retries = max_retries
        self._context = _build_context(environment, service_name)
        self._transport: AsyncHttpTransport | None = None
        self._queue: asyncio.Queue[LogWire | None] = asyncio.Queue(maxsize=max_queue_size)
        self._pending: list[LogWire] = []
        self._lock = asyncio.Lock()
        self._worker_task: asyncio.Task[None] | None = None
        self._closed = False

    async def __aenter__(self) -> "AsyncOliraClient":
        self._transport = AsyncHttpTransport(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=self._timeout,
            max_retries=self._max_retries,
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
        event_type: OliraEventType,
        patient_id: str,
        payload: dict[str, Any],
        trace: OliraTrace | None = None,
        timestamp: str | None = None,
    ) -> None:
        event = LogWire(
            event_name=event_type.value,
            patient_id=patient_id,
            payload=payload,
            context=self._context,
            trace=trace,
            timestamp=timestamp,
        )
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def log(
        self,
        *,
        event_type: OliraEventType,
        patient_id: str,
        payload: dict[str, Any] | None = None,
        trace: OliraTrace | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Enqueue an event for background delivery."""
        self._emit(event_type, patient_id, payload or {}, trace=trace, timestamp=timestamp)

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
            event = LogWire(
                event_name=spec.event_type.value,
                patient_id=spec.patient_id,
                payload=spec.payload or {},
                context=self._context,
                trace=spec.trace,
                timestamp=spec.timestamp,
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

    async def delete_patient(self, *, patient_id: str) -> None:
        """Soft-delete a patient. Requires api:manage-patients scope."""
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling delete_patient()"
            )
        await self._transport.delete_patient(patient_id)

    async def get_patient_token(self, *, patient_id: str) -> PatientToken:
        """Mint a short-lived patient-scoped JWT. Requires sdk:patient-token scope."""
        if self._transport is None:
            raise ValidationError(
                "AsyncOliraClient must be used as an async context manager before calling get_patient_token()"
            )
        return await self._transport.get_patient_token({"patient_id": patient_id})

    # --- State-read methods (sdk:state-read scope) ---

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

    async def list_summaries(self, *, patient_id: str) -> list[SummaryMeta]:
        """List available summaries for the patient. Requires sdk:state-read scope."""
        transport = self._require_transport("list_summaries")
        raw = await transport.list_summaries(patient_id)
        return [SummaryMeta.model_validate(s) for s in raw]

    async def list_summary_blocks(self, *, patient_id: str, summary_type: str) -> SummaryBlocksListResult:
        """List blocks within a specific summary. Requires sdk:state-read scope."""
        transport = self._require_transport("list_summary_blocks")
        return await transport.list_summary_blocks(patient_id, summary_type)

    async def get_summary(
        self,
        *,
        patient_id: str,
        summary_type: str,
    ) -> SummaryResult:
        """Get a summary snapshot. Requires sdk:state-read scope.

        Returns the unified block list under ``content["blocks"]`` (v2 model),
        plus ``content["temp"]`` when live entries are present.
        """
        transport = self._require_transport("get_summary")
        return await transport.get_summary(patient_id, summary_type)

    async def get_summary_block(
        self,
        *,
        patient_id: str,
        summary_type: str,
        block_id: str,
    ) -> SummaryBlockResult:
        """Get a specific block from a summary. Requires sdk:state-read scope."""
        transport = self._require_transport("get_summary_block")
        return await transport.get_summary_block(patient_id, summary_type, block_id)

    async def get_summary_recent_events(
        self,
        *,
        patient_id: str,
        summary_type: str,
        limit: int = 50,
    ) -> SummaryRecentEventsResult:
        """Get recent TEMP events for a summary type. Requires sdk:state-read scope."""
        transport = self._require_transport("get_summary_recent_events")
        return await transport.get_summary_recent_events(patient_id, summary_type, {"limit": limit})

    async def get_event_logs(
        self,
        *,
        patient_id: str,
        since: str | None = None,
        limit: int = 50,
        event_types: list[str] | None = None,
        trace_type: str | None = None,
        trace_id: str | None = None,
    ) -> EventLogsResult:
        """Get event logs for the patient. Requires sdk:state-read scope."""
        transport = self._require_transport("get_event_logs")
        params: dict[str, Any] = {"limit": limit}
        if since:
            params["since"] = since
        if event_types:
            params["event_types"] = ",".join(event_types)
        if trace_type:
            params["trace_type"] = trace_type
        if trace_id:
            params["trace_id"] = trace_id
        return await transport.get_event_logs(patient_id, params)

    async def get_state_transitions(
        self,
        *,
        patient_id: str,
        since: str | None = None,
        event_log_type: str | None = None,
        trace_type: str | None = None,
        trace_id: str | None = None,
        status: str = "complete",
        limit: int = 50,
    ) -> StateTransitionsResult:
        """Get state transitions for the patient. Requires sdk:state-read scope."""
        transport = self._require_transport("get_state_transitions")
        params: dict[str, Any] = {"status": status, "limit": limit}
        if since:
            params["since"] = since
        if event_log_type:
            params["event_log_type"] = event_log_type
        if trace_type:
            params["trace_type"] = trace_type
        if trace_id:
            params["trace_id"] = trace_id
        return await transport.get_state_transitions(patient_id, params)

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

    async def flush(self) -> None:
        drained: list[LogWire] = []
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
