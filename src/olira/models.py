"""Event schemas, types, and internal Event wire format.

Field shapes align with packages/common-models/.../schemas/personalization/util.py
(source of truth). The SDK does not depend on common-models so it remains
public and PyPI-installable.
"""

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from .exceptions import ValidationError

# Max payload size per event (512 KB) — SPEC Section 9.1
MAX_EVENT_PAYLOAD_BYTES = 512 * 1024

# PII patterns: empty/whitespace, email (@), US phone (10 digits), SSN (xxx-xx-xxxx)
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


class OliraEventType(StrEnum):
    """Customer-facing event types. Values match the platform event log catalog."""

    # Symptom reports
    SYMPTOM_REPORT = "symptom_report"
    SYMPTOM_FREE_TEXT = "symptom_free_text"
    SYMPTOM_DETAIL = "symptom_detail"
    MOODS_REPORT = "moods_report"
    FUNCTIONAL_CLASS_REPORTED = "functional_class_reported"
    HEALTH_METRIC_REPORTED = "health_metric_reported"

    # Lab & clinical
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
    MEMORY_REPORT = "memory_report"
    UNSTRUCTURED_REPORT_RECEIVED = "unstructured_report_received"

    # Questionnaires
    QUESTIONNAIRE_RESPONSE = "questionnaire_response"
    QUESTIONNAIRE_ITEM_RESPONSE = "questionnaire_item_response"

    # Conversations
    CONVERSATION_COMPLETED = "conversation_completed"
    CONVERSATION_TURN_LOGGED = "conversation_turn_logged"

    # Passive data
    HEART_RATE_DATA_RECEIVED = "heart_rate_data_received"
    SLEEP_DATA_RECEIVED = "sleep_data_received"
    ACTIVITY_DATA_RECEIVED = "activity_data_received"
    CGM_READING_RECEIVED = "cgm_reading_received"
    SPO2_READING_RECEIVED = "spo2_reading_received"
    WEIGHT_MEASUREMENT_RECEIVED = "weight_measurement_received"

    # Medications
    MEDICATION_ACTION = "medication_action"
    MEDICATION_DOSE_UPDATE = "medication_dose_update"
    MEDICATION_ADVERSE_EVENT_REPORTED = "medication_adverse_event_reported"

    # Engagement
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    CONTENT_INTERACTED = "content_interacted"
    NOTIFICATION_INTERACTED = "notification_interacted"
    TASK_UPDATED = "task_updated"
    INTERACTION_FEEDBACK = "interaction_feedback"
    FEATURE_USED = "feature_used"

    # Profile
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
    """Links an event to an object in your own system (e.g. a conversation or message).

    ``object_id`` is your identifier for that object — the same string you would use
    to look it up in your own database.  It is stored and returned as-is and is never
    interpreted or validated by Olira.
    """

    object_type: str = Field(..., description="Category of the linked object, e.g. 'conversation' or 'message'")
    object_id: str = Field(..., description="Your identifier for the linked object")


# --- Public API schemas (exported from olira); shapes match common-models util.py ---


class EsasItem(BaseModel):
    """
    Single ESAS-r symptom item (name + score 0–10).
    Shape matches EsasSymptomItem in common-models util.py.
    Optional type/snomed_code/meddra_code used for matching server-side.
    """

    name: str = Field(..., description="ESAS item name (display); not used for matching")
    score: int = Field(..., ge=0, le=10, description="Score 0–10")
    type: str | None = Field(
        default=None,
        description="Symptom type for matching when snomed_code and meddra_code unset (e.g. pain, nausea)",
    )
    snomed_code: str | None = Field(default=None, description="SNOMED CT code; first choice for matching")
    meddra_code: str | None = Field(default=None, description="MedDRA code; used when snomed_code unset")


class LabResultItem(BaseModel):
    """
    One result item from lab_results_received.results[] (with or without LOINC).
    Shape matches LabResultItem in common-models util.py.
    At least one of loinc_code or test_name; at least one of value_numeric or value_string.
    """

    loinc_code: str | None = Field(
        default=None,
        description="LOINC code when available; test_name/specimen resolved server-side",
    )
    test_name: str | None = Field(default=None, description="Required when loinc_code not provided")
    specimen_type: str | None = Field(default=None, description="Optional when no LOINC")
    test_category: str | None = Field(default=None, description="e.g. hematology, metabolic, lipid")
    value_numeric: float | None = Field(default=None, description="Quantitative result")
    value_string: str | None = Field(default=None, description="Non-quantitative result")
    unit: str = Field(default="", description="Unit of measure (prefer explicit e.g. g/dL)")
    abnormal_flag: str | None = Field(default=None, description="H, L, N, HH, LL")
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    result_status: str | None = Field(default=None, description="final, preliminary, corrected")

    @model_validator(mode="after")
    def check_identifier_and_value(self) -> Self:
        if not self.loinc_code and not self.test_name:
            raise ValueError("at least one of loinc_code or test_name is required")
        if self.value_numeric is None and self.value_string is None:
            raise ValueError("at least one of value_numeric or value_string is required")
        return self


class PerformingLab(BaseModel):
    """Performing lab from lab_results_received envelope. Shape matches common-models util.py."""

    name: str | None = Field(default=None)
    clia_number: str | None = Field(default=None)


class TimePeriod(BaseModel):
    """Time range in ISO 8601 datetimes. Wire-compatible with PeriodRange in common-models util.py."""

    start_datetime: str
    end_datetime: str


# --- Batch API types ---


@dataclass
class LogSpec:
    """Lightweight log specification for log_batch(). Not persisted internally."""

    event_type: OliraEventType
    patient_id: str
    payload: dict[str, Any] | None = None
    trace: OliraTrace | None = None
    timestamp: str | None = None
    idempotency_key: str | None = None


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


# --- Internal wire format (not exported) ---


class LogWire(BaseModel):
    """Wire-format log entry; built by the SDK, not by customers."""

    event_name: str
    patient_id: str
    timestamp: str | None = None
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, str] = Field(default_factory=dict)
    trace: OliraTrace | None = None

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v: str) -> str:
        return _validate_patient_id(v)

    @model_validator(mode="after")
    def check_payload_size(self) -> Self:
        body = self.model_dump_json()
        if len(body.encode("utf-8")) > MAX_EVENT_PAYLOAD_BYTES:
            raise ValidationError(
                f"Event payload exceeds {MAX_EVENT_PAYLOAD_BYTES // 1024} KB limit; "
                "truncate or chunk the payload before sending"
            )
        return self


# --- Patient management request types (exported) ---


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


# --- Patient management response types (exported) ---


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
