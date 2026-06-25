"""Pydantic models and wire types for Olira event ingestion and patient APIs."""

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from .exceptions import ValidationError

MAX_EVENT_PAYLOAD_BYTES = 512 * 1024
_SUBJECT_ID_EMPTY = re.compile(r"^\s*$")
_SUBJECT_ID_EMAIL = re.compile(r"@")
_SUBJECT_ID_US_PHONE = re.compile(r"^\d{10}$")
_SUBJECT_ID_SSN = re.compile(r"^\d{3}-\d{2}-\d{4}$")


def _validate_patient_id(value: str) -> str:
    """Raise ValidationError if patient_id is empty or matches PII patterns."""
    if _SUBJECT_ID_EMPTY.match(value):
        raise ValidationError("patient_id cannot be empty or whitespace")
    if _SUBJECT_ID_EMAIL.search(value):
        raise ValidationError("patient_id must not contain email addresses; use a pseudonymous identifier")
    stripped = value.strip().replace("-", "").replace(" ", "")
    if _SUBJECT_ID_US_PHONE.match(stripped) and len(stripped) == 10:
        raise ValidationError("patient_id must not contain US phone numbers; use a pseudonymous identifier")
    if _SUBJECT_ID_SSN.match(value.strip()):
        raise ValidationError("patient_id must not contain SSN; use a pseudonymous identifier")
    return value


class OliraLogType(StrEnum):
    """Customer-facing log types. Values match the platform log catalog."""

    SYMPTOM_REPORT = "symptom_report"
    SYMPTOM_FREE_TEXT = "symptom_free_text"
    SYMPTOM_DETAIL = "symptom_detail"
    MOODS_REPORT = "moods_report"
    FUNCTIONAL_CLASS_REPORTED = "functional_class_reported"
    HEALTH_METRIC_REPORTED = "health_metric_reported"

    LAB_RESULTS_RECEIVED = "lab_results_received"
    VITALS_MEASUREMENT = "vitals_measurement"
    CLINICAL_NOTE_RECEIVED = "clinical_note_received"
    CLINICAL_FINDING_REPORTED = "clinical_finding_reported"
    PROCEDURE_RESULT_RECEIVED = "procedure_result_received"
    PROCEDURE_PERFORMED = "procedure_performed"
    GENOMIC_VARIANT_REPORTED = "genomic_variant_reported"
    IMAGING_RESULT_RECEIVED = "imaging_result_received"
    CLINICAL_MEASUREMENT_REPORTED = "clinical_measurement_reported"
    TREATMENT_RESPONSE_ASSESSMENT_REPORTED = "treatment_response_assessment_reported"
    CLINICAL_PLAN_ITEM_REPORTED = "clinical_plan_item_reported"
    CARE_ENCOUNTER_REPORTED = "care_encounter_reported"
    CARE_GOAL_REPORTED = "care_goal_reported"
    IMMUNIZATION_REPORTED = "immunization_reported"
    ALLERGY_INTOLERANCE_REPORTED = "allergy_intolerance_reported"
    FAMILY_HISTORY_REPORTED = "family_history_reported"
    DEVICE_REPORTED = "device_reported"
    CARE_ACTION_LOGGED = "care_action_logged"
    MEMORY_REPORT = "memory_report"
    UNSTRUCTURED_REPORT_RECEIVED = "unstructured_report_received"

    QUESTIONNAIRE_RESPONSE = "questionnaire_response"
    QUESTIONNAIRE_ITEM_RESPONSE = "questionnaire_item_response"

    CONVERSATION_COMPLETED = "conversation_completed"
    CONVERSATION_TURN_LOGGED = "conversation_turn_logged"

    HEART_RATE_DATA_RECEIVED = "heart_rate_data_received"
    SLEEP_DATA_RECEIVED = "sleep_data_received"
    ACTIVITY_DATA_RECEIVED = "activity_data_received"
    CGM_READING_RECEIVED = "cgm_reading_received"
    SPO2_READING_RECEIVED = "spo2_reading_received"
    WEIGHT_MEASUREMENT_RECEIVED = "weight_measurement_received"

    MEDICATION_ACTION = "medication_action"
    MEDICATION_DOSE_UPDATE = "medication_dose_update"
    MEDICATION_ADVERSE_EVENT_REPORTED = "medication_adverse_event_reported"

    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    CONTENT_INTERACTED = "content_interacted"
    NOTIFICATION_INTERACTED = "notification_interacted"
    TASK_UPDATED = "task_updated"
    INTERACTION_FEEDBACK = "interaction_feedback"
    FEATURE_USED = "feature_used"

    DEMOGRAPHICS_UPDATED = "demographics_updated"
    CONDITION_RECORDED = "condition_recorded"
    PREFERENCES_UPDATED = "preferences_updated"
    EMERGENCY_CONTACT_UPDATED = "emergency_contact_updated"
    CARE_TEAM_UPDATED = "care_team_updated"
    INSURANCE_UPDATED = "insurance_updated"
    SOCIAL_UPDATED = "social_updated"
    PHARMACY_UPDATED = "pharmacy_updated"
    TREATMENT_PHASE_CHANGED = "treatment_phase_changed"


class OliraTrace(BaseModel):
    """Links a log to an object in your own system (e.g. a conversation or message).

    ``object_id`` is your identifier for that object — the same string you would use
    to look it up in your own database.  It is stored and returned as-is and is never
    interpreted or validated by Olira.

    """

    object_type: str | None = Field(
        default=None,
        description="Category of the linked object, e.g. 'conversation' or 'message'",
    )
    object_id: str | None = Field(default=None, description="Your identifier for the linked object")


@dataclass
class LogSpec:
    """Lightweight log specification for log_batch()."""

    log_type: OliraLogType
    patient_id: str
    payload: dict[str, Any] | None = None
    trace: OliraTrace | None = None
    timestamp: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] | None = None


class BatchError(BaseModel):
    """Per-event error from a batch response."""

    index: int
    code: str
    message: str


class BatchResult(BaseModel):
    """Result of a log_batch() call. Mirrors /v1/logs/batch response."""

    accepted: int
    failed: int
    errors: list[BatchError] = Field(default_factory=list)


class _LogWire(BaseModel):
    """Wire-format log entry built by the SDK for batch transport (512 KB max per event)."""

    log_type: str
    patient_id: str
    timestamp: str | None = None
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None
    context: dict[str, str] = Field(default_factory=dict)
    trace: OliraTrace | None = None

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v: str) -> str:
        return _validate_patient_id(v)

    @model_validator(mode="after")
    def check_payload_size(self) -> Self:
        if self.trace is not None:
            if not self.trace.object_type or not self.trace.object_id:
                raise ValueError("trace requires both object_type and object_id")
        body = self.model_dump_json()
        if len(body.encode("utf-8")) > MAX_EVENT_PAYLOAD_BYTES:
            raise ValidationError(
                f"Event payload exceeds {MAX_EVENT_PAYLOAD_BYTES // 1024} KB limit; "
                "truncate or chunk the payload before sending"
            )
        return self


class ExternalIdentifier(BaseModel):
    """Links a patient to their ID in an external system (e.g. Epic MRN, Flatiron ID, FHIR resource ID)."""

    system: str = Field(..., description="System name, e.g. 'epic', 'flatiron', 'fhir'")
    value: str = Field(..., description="Patient ID in that system")


class CreatePatientRequest(BaseModel):
    """Request body for creating a patient.

    Demographics are optional so you can create **shell** patients (e.g. external id
    only), matching the API. You must send at least one of: ``external_identifiers``,
    ``email``, ``phone_number``, ``first_name``, ``last_name``, or ``date_of_birth``.
    Olira assigns a stable ``id`` at creation time — it is returned in the :class:`Patient` response.
    """

    first_name: str | None = Field(default=None, description="Given name; omit for shell patients.")
    last_name: str | None = Field(default=None, description="Family name; omit for shell patients.")
    email: str | None = None
    phone_number: str | None = None
    date_of_birth: str | None = Field(
        default=None,
        description="ISO 8601 datetime string, e.g. '1985-03-22T00:00:00Z'",
    )
    sex: str = "unknown"
    timezone: str = Field(default="UTC", description="IANA timezone, e.g. America/New_York")
    primary_disease_site: str | None = None
    disease_stage: str | None = None
    external_identifiers: list[ExternalIdentifier] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _strip_names(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        raise ValueError(f"Expected a string, got {type(v).__name__}")

    @model_validator(mode="after")
    def _require_anchor_field(self) -> Self:
        has_ext = bool(self.external_identifiers)
        has_email = self.email is not None
        has_phone = bool(self.phone_number and str(self.phone_number).strip())
        has_name = self.first_name is not None or self.last_name is not None
        has_dob = bool(self.date_of_birth and str(self.date_of_birth).strip())
        if not any((has_ext, has_email, has_phone, has_name, has_dob)):
            raise ValueError(
                "Provide at least one of: external_identifiers, email, phone_number, "
                "first_name, last_name, or date_of_birth"
            )
        return self


class UpdatePatientRequest(BaseModel):
    """Request body for updating a patient (all fields optional).

    Only the fields you set are changed; omitted fields are left as-is.
    """

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    sex: str | None = None
    timezone: str | None = None
    primary_disease_site: str | None = None
    disease_stage: str | None = None
    external_identifiers: list[ExternalIdentifier] | None = None
    metadata: dict[str, Any] | None = None


class Patient(BaseModel):
    """A patient in your organisation.

    `id` is the Olira-assigned identifier for this patient, returned at creation
    time.  Use it in all subsequent calls that reference this patient.
    """

    id: str
    first_name: str | None = None
    last_name: str | None = None
    sex: str | None = None
    timezone: str
    status: str
    email: str | None = None
    phone_number: str | None = None
    date_of_birth: str | None = None
    primary_disease_site: str | None = None
    disease_stage: str | None = None
    created_at: str | None = None
    external_identifiers: list[ExternalIdentifier] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class PatientListResult(BaseModel):
    """Result of a list_patients() call."""

    patients: list[Patient]
    total: int
    has_more: bool


class PatientBatchItem(BaseModel):
    """One successfully created patient from a batch_create_patients() call."""

    index: int
    id: str
    source: str | None = None


class PatientBatchResult(BaseModel):
    """Result of a create_patients_batch() call. Mirrors /v1/patients/batch response."""

    count: int
    items: list[PatientBatchItem]
    errors: list[BatchError] = Field(default_factory=list)


class PatientToken(BaseModel):
    """A short-lived patient-scoped JWT returned by get_patient_token().

    Pass `access_token` as a Bearer token to the Olira MCP Patient State server.
    The token is locked to the patient identified by the `patient_id` you supplied
    and expires after `expires_in` seconds (default 15 minutes).
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    scopes: list[str]


class StableModule(BaseModel):
    """One stable state module (demographics, condition_diagnosis, medications, user_preferences)."""

    module_type: str
    payload: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class StableDataResult(BaseModel):
    """Result of get_stable_data(). Modules keyed by module_type."""

    patient_id: str
    modules: dict[str, StableModule]


class EventStateModuleSummary(BaseModel):
    """Metadata entry for a single event state module returned by list_event_state_modules()."""

    module_type: str
    updated_at: str | None = None
    created_at: str | None = None


class EventStateModuleResult(BaseModel):
    """Result of get_event_state_module()."""

    patient_id: str
    module_type: str
    payload: dict[str, Any] | list[Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ViewMeta(BaseModel):
    """Metadata entry for a view returned by list_views().

    ``has_blocks`` reflects the unified block list (current v2 model).
    ``has_temp`` reflects whether live append-only TEMP entries exist.
    """

    view_type: str
    view_id: str
    has_blocks: bool = False
    has_temp: bool = False


class ViewBlockMeta(BaseModel):
    """Metadata for one block within a view returned by list_view_blocks()."""

    block_id: str | None = None
    block_name: str | None = None
    has_result: bool = False


class ViewBlocksListResult(BaseModel):
    """Result of list_view_blocks(). Blocks come from the unified block list."""

    patient_id: str
    view_type: str
    blocks: list[ViewBlockMeta] = Field(default_factory=list)


class ViewResult(BaseModel):
    """Result of get_view().

    ``content`` holds the unified block list under the key ``blocks`` (current v2 model),
    plus ``temp`` entries when present. Legacy snapshots may also include ``week``,
    ``long_term``, or ``persistent`` keys.
    """

    patient_id: str
    view_type: str
    view_id: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)


class ViewBlockResult(BaseModel):
    """Result of get_view_block()."""

    patient_id: str
    view_type: str
    block_id: str
    content: str | None = None
    confidences: dict[str, float] | None = None
    updated_at: str | None = None


class ViewRecentEventsResult(BaseModel):
    """Result of get_view_recent_events(). Entries are the TEMP segment string list."""

    patient_id: str
    view_type: str
    entries: list[str] = Field(default_factory=list)
    count: int = 0
    total_count: int = 0


class LogEntry(BaseModel):
    """One event log entry returned by get_logs()."""

    id: str
    type: str | None = None
    timestamp: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    trace: OliraTrace | None = None


class LogsResult(BaseModel):
    """Result of get_logs()."""

    patient_id: str
    count: int
    logs: list[LogEntry] = Field(default_factory=list)


class LogQueryResult(BaseModel):
    """Result of LogQuery.execute(). Mirrors POST /v1/state/.../logs/query."""

    count: int
    rows: list[dict[str, Any]] = Field(default_factory=list)
    organization_id: str | None = None
    patient_id: str | None = None
    total_count: int | None = None
    has_more: bool | None = None

    def __iter__(self) -> Any:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> dict[str, Any]:
        return self.rows[i]

    def as_logs(self) -> list["LogEntry"]:
        """Validate rows into typed LogEntry. Only valid when no .select() was used."""
        return [LogEntry.model_validate(r) for r in self.rows]


class EventEntry(BaseModel):
    """One event returned by get_events()."""

    id: str
    trigger: str | None = None
    log_type: str | None = None
    status: str | None = None
    triggered_at: str | None = None
    completed_at: str | None = None
    source_event_log_id: str | None = None
    log_payload: dict[str, Any] | None = None
    changes: list[dict[str, Any]] | None = None


class EventsResult(BaseModel):
    """Result of get_events()."""

    patient_id: str
    count: int
    events: list[EventEntry] = Field(default_factory=list)


class MemoryEntry(BaseModel):
    """One memory record returned by read_memories()."""

    memory_id: str
    content: str
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MemoriesResult(BaseModel):
    """Result of read_memories()."""

    patient_id: str
    count: int
    results: list[MemoryEntry] = Field(default_factory=list)


class IngestionJobStatus(StrEnum):
    """Lifecycle status of a HistoricalIngestionJob."""

    QUEUED = "queued"
    VALIDATING = "validating"
    INSERTING_PATIENTS = "inserting_patients"
    INSERTING_LOGS = "inserting_logs"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    REPLAYING = "replaying"
    BACKFILLING = "backfilling"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionRowError(BaseModel):
    """A single per-row error from an ingestion job (validation or insert failure)."""

    line: int = Field(..., description="1-indexed line number in the JSONL file (0 = non-row error)")
    code: str = Field(..., description="Machine-readable error code, e.g. 'missing_patient'")
    message: str = Field(..., description="Human-readable description")


class IngestionJob(BaseModel):
    """A historical data ingestion job returned by the API."""

    job_id: str
    status: IngestionJobStatus
    stage: str
    progress_pct: float = 0.0
    require_confirmation: bool = True
    summary_types: list[str] = Field(default_factory=list)
    patients_total: int = 0
    patients_processed: int = 0
    logs_total: int = 0
    logs_processed: int = 0
    logs_failed: int = 0
    logs_by_event_type: dict[str, int] = Field(default_factory=dict)
    patient_log_counts: dict[str, int] = Field(default_factory=dict)
    patient_event_type_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    patient_replay_statuses: dict[str, str] = Field(default_factory=dict)
    error_summary: list[IngestionRowError] = Field(default_factory=list)
    missing_template_slots: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "patient_id → list of summary_type keys missing a view slot. "
            "Present at AWAITING_CONFIRMATION when affected patients exist."
        ),
    )
    estimated_seconds_remaining: int | None = None
    view_backfill_job_id: str | None = None
    backfill_status: str | None = None
    backfill_progress_pct: float | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class IngestionJobListResult(BaseModel):
    """Result of list_ingestion_jobs()."""

    total: int
    jobs: list[IngestionJob] = Field(default_factory=list)


@dataclass
class IngestLogSpec:
    """Specification for a single log record in a historical ingestion job.

    ``event_type`` must be a valid platform event type string (e.g. ``"symptom_report"``).
    ``patient_id`` may be an Olira patient UUID or an ``external_identifier`` value present
    in the same file or already in the org.
    ``idempotency_key`` prevents duplicate insertion if the same file is re-submitted.
    ``trace`` is optional provenance (same shape as live ``log()``); when set, both
    ``object_type`` and ``object_id`` must be non-empty strings.
    """

    event_type: str
    patient_id: str
    timestamp: str
    payload: dict[str, Any] | None = None
    idempotency_key: str | None = None
    trace: OliraTrace | None = None


class IngestRecord(BaseModel):
    """A single record in a historical ingestion payload (patient or log).

    Build via the factory methods rather than constructing directly::

        IngestRecord.patient(CreatePatientRequest(...))
        IngestRecord.log(IngestLogSpec(...))
    """

    type: str
    data: dict[str, Any]

    @classmethod
    def patient(cls, req: "CreatePatientRequest") -> "IngestRecord":
        """Create a patient record from a :class:`CreatePatientRequest`."""
        return cls(type="patient", data=req.model_dump(exclude_none=True))

    @classmethod
    def log(cls, spec: IngestLogSpec) -> "IngestRecord":
        """Create a log record from an :class:`IngestLogSpec`."""
        data: dict[str, Any] = {
            "event_type": spec.event_type,
            "patient_id": spec.patient_id,
            "timestamp": spec.timestamp,
        }
        if spec.payload:
            data["payload"] = spec.payload
        if spec.idempotency_key:
            data["idempotency_key"] = spec.idempotency_key
        if spec.trace is not None:
            if not spec.trace.object_type or not spec.trace.object_id:
                raise ValidationError("trace requires both object_type and object_id")
            data["trace"] = {
                "object_type": spec.trace.object_type,
                "object_id": spec.trace.object_id,
            }
        return cls(type="log", data=data)


# ---------------------------------------------------------------------------
# Cohort models
# ---------------------------------------------------------------------------


class Cohort(BaseModel):
    """A named patient cohort returned by create/get/update cohort operations."""

    id: str
    name: str
    description: str | None = None
    patient_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class CohortListItem(BaseModel):
    """Summary entry returned by list_cohorts()."""

    id: str
    name: str
    description: str | None = None
    patient_count: int = 0
    template_assignment_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class CohortListResult(BaseModel):
    """Result of list_cohorts()."""

    data: list[CohortListItem] = Field(default_factory=list)


class CohortPatientMutationResult(BaseModel):
    """Result of add_patients_to_cohort() and remove_patients_from_cohort()."""

    cohort_id: str
    patient_count: int


class CohortTemplateAssignment(BaseModel):
    """One template assignment returned by assign/list cohort template operations."""

    id: str
    summary_type: str
    template_id: str
    cohort_id: str
    assigned_at: str | None = None


class CohortTemplatesResult(BaseModel):
    """Result of list_cohort_templates()."""

    data: list[CohortTemplateAssignment] = Field(default_factory=list)


class CohortDeleteResult(BaseModel):
    """Result of delete_cohort()."""

    deleted: bool
    cohort_id: str
