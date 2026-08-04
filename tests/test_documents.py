"""SDK document upload helper tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from olira.documents import DocumentLogType, DocumentResource, DocumentStatus, upload_document_via_transport
from olira.exceptions import ValidationError


class FakeTransport:
    def __init__(self) -> None:
        self.upload_bodies: list[dict] = []
        self.puts: list[tuple[str, bytes, dict[str, str] | None]] = []
        self.commits: list[str] = []
        self._docs: dict[str, DocumentResource] = {}

    def get_document_upload_url(self, body: dict) -> dict:
        self.upload_bodies.append(body)
        doc_id = "doc-1"
        self._docs[doc_id] = DocumentResource(
            document_id=doc_id,
            status=DocumentStatus.PENDING_UPLOAD,
            filename=body["filename"],
            patient_id=body["patient_id"],
            log_type=body["log_type"],
            document_type=body.get("document_type"),
            note_type=body.get("note_type"),
            s3_uri="s3://bucket/key",
        )
        return {
            "document_id": doc_id,
            "upload_url": "https://example.com/put",
            "s3_bucket": "bucket",
            "s3_key": "key",
            "expires_in": 900,
        }

    def put_presigned(self, url: str, blob: bytes, headers: dict[str, str] | None = None) -> None:
        self.puts.append((url, blob, headers))

    def commit_document(self, document_id: str) -> dict:
        self.commits.append(document_id)
        doc = self._docs[document_id]
        self._docs[document_id] = doc.model_copy(update={"status": DocumentStatus.OCR_RUNNING})
        return {"document_id": document_id, "status": "ocr_running", "workflow_id": f"document-ocr-{document_id}"}

    def get_document(self, document_id: str) -> DocumentResource:
        return self._docs[document_id]


def test_upload_document_via_transport(tmp_path: Path) -> None:
    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")
    transport = FakeTransport()

    handle = upload_document_via_transport(
        transport,
        patient_id="p1",
        path=pdf,
        log_type=DocumentLogType.UNSTRUCTURED_REPORT,
        document_type="clinical_note",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        idempotency_key="k1",
    )

    assert handle.document_id == "doc-1"
    assert transport.puts and transport.commits == ["doc-1"]
    assert transport.puts[0][2] == {"Content-Type": "application/pdf"}
    assert transport.upload_bodies[0]["document_type"] == "clinical_note"
    assert handle.document.status == DocumentStatus.OCR_RUNNING


def test_upload_requires_document_type(tmp_path: Path) -> None:
    pdf = tmp_path / "note.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValidationError, match="document_type"):
        upload_document_via_transport(
            FakeTransport(),
            patient_id="p1",
            path=pdf,
            log_type="unstructured_report",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            idempotency_key="k1",
        )
