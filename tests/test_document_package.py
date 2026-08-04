"""SDK document-package (documents=) helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from olira import AsyncOliraClient, OliraClient, OliraEnv
from olira.exceptions import ServerError, ValidationError
from olira.models import (
    CreatePatientRequest,
    ExternalIdentifier,
    IngestDocument,
    IngestionJob,
    IngestLogSpec,
    IngestRecord,
)
from olira.validation import validate_ingestion_records


def _ingestion_job(job_id: str = "job-1") -> IngestionJob:
    return IngestionJob.model_validate(
        {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "progress_pct": 0.0,
        }
    )


def _pdf(tmp_path: Path, name: str = "note.pdf") -> Path:
    pdf = tmp_path / name
    pdf.write_bytes(b"%PDF-1.4")
    return pdf


def _doc(path: Path, *, ref_id: str | None = None) -> IngestDocument:
    return IngestDocument(
        path=str(path),
        patient_id="ext-1",
        log_type="unstructured_report",
        document_type="radiology_report",
        timestamp="2024-03-15T10:00:00Z",
        ref_id=ref_id,
        idempotency_key=f"ext-1:doc:{ref_id or 'auto'}",
    )


class DocumentPackageTransport:
    """Sync transport fake for document-package orchestration."""

    def __init__(self, *, fail_put: bool = False) -> None:
        self.fail_put = fail_put
        self.begin_bodies: list[dict] = []
        self.puts: list[tuple[str, bytes, dict[str, str] | None]] = []
        self.create_bodies: list[dict] = []

    def begin_ingestion_job(self, body: dict) -> dict:
        self.begin_bodies.append(body)
        docs = [
            {
                "ref_id": d["ref_id"],
                "upload_url": f"https://example.com/put/{d['ref_id']}",
                "s3_key": f"org/job/documents/{d['ref_id']}.pdf",
            }
            for d in body["documents"]
        ]
        return {
            "job_id": "job-1",
            "manifest_upload_url": "https://example.com/put/manifest",
            "manifest_s3_key": "org/job/manifest.jsonl",
            "documents": docs,
        }

    def put_presigned(self, url: str, blob: bytes, headers: dict[str, str] | None = None) -> None:
        if self.fail_put:
            raise ServerError("Presigned upload failed (HTTP 403)", status_code=403)
        self.puts.append((url, blob, headers))

    def create_ingestion_job(self, body: dict) -> IngestionJob:
        self.create_bodies.append(body)
        return _ingestion_job(body.get("job_id", "job-1"))

    def close(self) -> None:
        pass


class AsyncDocumentPackageTransport(DocumentPackageTransport):
    """Async transport fake — same recording, awaitable methods."""

    async def begin_ingestion_job(self, body: dict) -> dict:  # type: ignore[override]
        return DocumentPackageTransport.begin_ingestion_job(self, body)

    async def put_presigned(  # type: ignore[override]
        self, url: str, blob: bytes, headers: dict[str, str] | None = None
    ) -> None:
        DocumentPackageTransport.put_presigned(self, url, blob, headers)

    async def create_ingestion_job(self, body: dict) -> IngestionJob:  # type: ignore[override]
        return DocumentPackageTransport.create_ingestion_job(self, body)

    async def aclose(self) -> None:
        pass


def test_ingest_record_document_factory(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path)
    doc = IngestDocument(
        path=str(pdf),
        patient_id="ext-1",
        log_type="unstructured_report",
        document_type="radiology_report",
        timestamp="2024-03-15T10:00:00Z",
        idempotency_key="ext-1:doc:d1",
    )
    row = IngestRecord.document(doc, s3_key="documents/d1.pdf", ref_id="d1")
    assert row.type == "document"
    assert row.data["ref_id"] == "d1"
    assert row.data["s3_key"] == "documents/d1.pdf"
    assert row.data["document_type"] == "radiology_report"


def test_validate_document_record_ok(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path)
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
                document_type="radiology_report",
                timestamp="2024-03-15T10:00:00Z",
            ),
            s3_key="documents/d1.pdf",
            ref_id="d1",
        ),
    ]
    errors = [e for e in validate_ingestion_records(records) if e.code != "patient_id_not_in_file"]
    assert errors == []


def test_validate_document_requires_document_type(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path)
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


def test_create_document_package_uses_put_presigned(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path)
    client = OliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    transport = DocumentPackageTransport()
    client._transport = transport  # type: ignore[assignment]
    client._worker = None

    job = client.create_ingestion_job(documents=[_doc(pdf, ref_id="d1")], require_confirmation=False)

    assert job.job_id == "job-1"
    assert len(transport.begin_bodies) == 1
    assert len(transport.puts) == 2  # binary + manifest
    assert transport.puts[0][0] == "https://example.com/put/d1"
    assert transport.puts[0][2] == {"Content-Type": "application/pdf"}
    assert transport.puts[1][0] == "https://example.com/put/manifest"
    assert transport.create_bodies[0]["has_documents"] is True
    assert transport.create_bodies[0]["documents_total"] == 1
    client.close()


def test_duplicate_ref_id_raises_before_begin(tmp_path: Path) -> None:
    pdf_a = _pdf(tmp_path, "a.pdf")
    pdf_b = _pdf(tmp_path, "b.pdf")
    client = OliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    transport = DocumentPackageTransport()
    client._transport = transport  # type: ignore[assignment]
    client._worker = None

    with pytest.raises(ValidationError, match="Duplicate document ref_id"):
        client.create_ingestion_job(
            documents=[_doc(pdf_a, ref_id="same"), _doc(pdf_b, ref_id="same")],
        )

    assert transport.begin_bodies == []
    assert transport.puts == []
    client.close()


def test_failed_presigned_put_raises_before_create(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path)
    client = OliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    transport = DocumentPackageTransport(fail_put=True)
    client._transport = transport  # type: ignore[assignment]
    client._worker = None

    with pytest.raises(ServerError, match="Presigned upload failed"):
        client.create_ingestion_job(documents=[_doc(pdf, ref_id="d1")])

    assert transport.create_bodies == []
    client.close()


@pytest.mark.asyncio
async def test_async_rejects_document_rows_in_records(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path)
    doc = _doc(pdf, ref_id="d1")
    client = AsyncOliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT)
    transport = AsyncDocumentPackageTransport()
    client._transport = transport  # type: ignore[assignment]

    with pytest.raises(ValidationError, match="Pass document binaries via documents="):
        await client.create_ingestion_job(
            records=[IngestRecord.document(doc, s3_key="documents/d1.pdf", ref_id="d1")],
            documents=[doc],
        )

    assert transport.begin_bodies == []
    await client.aclose()


@pytest.mark.asyncio
async def test_async_duplicate_ref_id_raises(tmp_path: Path) -> None:
    pdf_a = _pdf(tmp_path, "a.pdf")
    pdf_b = _pdf(tmp_path, "b.pdf")
    client = AsyncOliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT)
    transport = AsyncDocumentPackageTransport()
    client._transport = transport  # type: ignore[assignment]

    with pytest.raises(ValidationError, match="Duplicate document ref_id"):
        await client.create_ingestion_job(
            documents=[_doc(pdf_a, ref_id="same"), _doc(pdf_b, ref_id="same")],
        )

    assert transport.begin_bodies == []
    await client.aclose()
