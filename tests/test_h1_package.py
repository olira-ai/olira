"""SDK H1 package (documents=) helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from olira.exceptions import ValidationError
from olira.models import CreatePatientRequest, ExternalIdentifier, IngestDocument, IngestLogSpec, IngestRecord
from olira.validation import validate_ingestion_records


def test_ingest_record_document_factory(tmp_path: Path) -> None:
    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    doc = IngestDocument(
        path=str(pdf),
        patient_id="ext-1",
        log_type="unstructured_report",
        document_type="clinical_note",
        timestamp="2024-03-15T10:00:00Z",
        idempotency_key="ext-1:doc:d1",
    )
    row = IngestRecord.document(doc, s3_key="documents/d1.pdf", ref_id="d1")
    assert row.type == "document"
    assert row.data["ref_id"] == "d1"
    assert row.data["s3_key"] == "documents/d1.pdf"
    assert row.data["document_type"] == "clinical_note"


def test_validate_document_record_ok(tmp_path: Path) -> None:
    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    records = [
        IngestRecord.patient(
            CreatePatientRequest(
                first_name="A",
                last_name="B",
                external_identifiers=[ExternalIdentifier(system="x", value="ext-1")],
            )
        ),
        IngestRecord.log(
            IngestLogSpec(
                event_type="symptom_report",
                patient_id="ext-1",
                timestamp="2024-03-15T14:00:00Z",
                payload={"instrument": "esas_r", "symptoms": [{"name": "fatigue", "score": 1}]},
            )
        ),
        IngestRecord.document(
            IngestDocument(
                path=str(pdf),
                patient_id="ext-1",
                log_type="unstructured_report",
                document_type="clinical_note",
                timestamp="2024-03-15T10:00:00Z",
            ),
            s3_key="documents/d1.pdf",
            ref_id="d1",
        ),
    ]
    errors = [e for e in validate_ingestion_records(records) if e.code != "patient_id_not_in_file"]
    assert errors == []


def test_validate_document_requires_document_type(tmp_path: Path) -> None:
    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    records = [
        IngestRecord.patient(
            CreatePatientRequest(
                first_name="A",
                last_name="B",
                external_identifiers=[ExternalIdentifier(system="x", value="ext-1")],
            )
        ),
        IngestRecord.document(
            IngestDocument(
                path=str(pdf),
                patient_id="ext-1",
                log_type="unstructured_report",
                timestamp="2024-03-15T10:00:00Z",
            ),
            s3_key="documents/d1.pdf",
            ref_id="d1",
        ),
    ]
    codes = {e.code for e in validate_ingestion_records(records)}
    assert "missing_document_type" in codes


def test_create_ingestion_job_rejects_sqs_with_documents(tmp_path: Path) -> None:
    from olira.client import OliraClient, OliraEnv

    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    client = OliraClient(api_key="test", base_url="http://localhost", environment=OliraEnv.DEVELOPMENT)
    # Force a transport so create doesn't fail earlier for missing key wiring in unit scope.
    with pytest.raises(ValidationError, match="temporal"):
        # Call the package helper directly with a fake body that sets sqs.
        client._create_h1_package_job(  # noqa: SLF001
            body={"processing_engine": "sqs", "require_confirmation": True},
            records=[],
            documents=[
                IngestDocument(
                    path=str(pdf),
                    patient_id="ext-1",
                    log_type="unstructured_report",
                    document_type="clinical_note",
                    timestamp="2024-03-15T10:00:00Z",
                )
            ],
        )
