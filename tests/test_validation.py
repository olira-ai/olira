"""Tests for historical ingestion validation."""

import json
from pathlib import Path

import pytest

from olira.exceptions import ValidationError
from olira.models import (
    CreatePatientRequest,
    ExternalIdentifier,
    IngestLogSpec,
    IngestRecord,
    OliraLogType,
    OliraTrace,
)
from olira.validation import validate_ingestion_file, validate_ingestion_records


def test_ingest_record_log_includes_trace():
    record = IngestRecord.log(
        IngestLogSpec(
            event_type=OliraLogType.SYMPTOM_REPORT.value,
            patient_id="MRN-12345",
            timestamp="2024-03-15T09:00:00Z",
            payload={"instrument": "esas_r", "symptoms": [{"name": "pain", "score": 3}]},
            trace=OliraTrace(object_type="emr_record", object_id="epic-encounter-98765"),
        )
    )
    assert record.data["trace"] == {
        "object_type": "emr_record",
        "object_id": "epic-encounter-98765",
    }


def test_ingest_record_log_omits_trace_when_unset():
    record = IngestRecord.log(
        IngestLogSpec(
            event_type=OliraLogType.SYMPTOM_REPORT.value,
            patient_id="MRN-12345",
            timestamp="2024-03-15T09:00:00Z",
        )
    )
    assert "trace" not in record.data


def test_ingest_record_log_rejects_incomplete_trace():
    with pytest.raises(ValidationError, match="trace requires both object_type and object_id"):
        IngestRecord.log(
            IngestLogSpec(
                event_type=OliraLogType.SYMPTOM_REPORT.value,
                patient_id="MRN-12345",
                timestamp="2024-03-15T09:00:00Z",
                trace=OliraTrace(object_type="emr_record", object_id=None),
            )
        )


def test_validate_ingestion_records_accepts_trace():
    records = [
        IngestRecord.patient(
            CreatePatientRequest(
                external_identifiers=[ExternalIdentifier(system="epic", value="MRN-12345")],
            )
        ),
        IngestRecord.log(
            IngestLogSpec(
                event_type=OliraLogType.SYMPTOM_REPORT.value,
                patient_id="MRN-12345",
                timestamp="2024-03-15T09:00:00Z",
                trace=OliraTrace(object_type="emr_record", object_id="epic-encounter-98765"),
            )
        ),
    ]
    assert validate_ingestion_records(records) == []


def test_validate_ingestion_records_rejects_invalid_trace():
    records = [
        IngestRecord(
            type="log",
            data={
                "event_type": OliraLogType.SYMPTOM_REPORT.value,
                "patient_id": "507f1f77bcf86cd799439011",
                "timestamp": "2024-03-15T09:00:00Z",
                "trace": {"object_type": "emr_record", "object_id": None},
            },
        )
    ]
    errors = validate_ingestion_records(records)
    assert len(errors) == 1
    assert errors[0].code == "invalid_trace"


def test_validate_ingestion_records_accepts_org_native_event_type():
    records = [
        IngestRecord(
            type="log",
            data={
                "event_type": "myorg_custom_event",
                "patient_id": "507f1f77bcf86cd799439011",
                "timestamp": "2024-03-15T09:00:00Z",
            },
        )
    ]
    assert validate_ingestion_records(records) == []


def test_validate_ingestion_records_flags_near_miss_platform_typo():
    records = [
        IngestRecord(
            type="log",
            data={
                "event_type": "symptom_repor",
                "patient_id": "507f1f77bcf86cd799439011",
                "timestamp": "2024-03-15T09:00:00Z",
            },
        )
    ]
    errors = validate_ingestion_records(records)
    assert len(errors) == 1
    assert errors[0].code == "unknown_event_type"
    assert "symptom_report" in errors[0].message


def test_validate_ingestion_records_rejects_non_string_event_type():
    records = [
        IngestRecord(
            type="log",
            data={
                "event_type": 12345,
                "patient_id": "507f1f77bcf86cd799439011",
                "timestamp": "2024-03-15T09:00:00Z",
            },
        )
    ]
    errors = validate_ingestion_records(records)
    assert len(errors) == 1
    assert errors[0].code == "invalid_event_type"


def test_validate_ingestion_file_flags_near_miss_platform_typo(tmp_path: Path):
    jsonl = tmp_path / "ingest.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "type": "log",
                "data": {
                    "event_type": "symptom_repor",
                    "patient_id": "507f1f77bcf86cd799439011",
                    "timestamp": "2024-03-15T09:00:00Z",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    errors = validate_ingestion_file(jsonl)
    assert len(errors) == 1
    assert errors[0].code == "unknown_event_type"
    assert "symptom_report" in errors[0].message


def test_validate_ingestion_file_rejects_non_string_event_type(tmp_path: Path):
    jsonl = tmp_path / "ingest.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "type": "log",
                "data": {
                    "event_type": 12345,
                    "patient_id": "507f1f77bcf86cd799439011",
                    "timestamp": "2024-03-15T09:00:00Z",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    errors = validate_ingestion_file(jsonl)
    assert len(errors) == 1
    assert errors[0].code == "invalid_event_type"


def test_validate_ingestion_file_accepts_trace(tmp_path: Path):
    jsonl = tmp_path / "ingest.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "patient",
                        "data": {
                            "external_identifiers": [{"system": "epic", "value": "MRN-12345"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "log",
                        "data": {
                            "event_type": "symptom_report",
                            "patient_id": "MRN-12345",
                            "timestamp": "2024-03-15T09:00:00Z",
                            "trace": {
                                "object_type": "emr_record",
                                "object_id": "epic-encounter-98765",
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert validate_ingestion_file(jsonl) == []
