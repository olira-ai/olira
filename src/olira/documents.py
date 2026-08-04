"""Clinical document upload: label → presigned PUT → commit → OCR → EventLog.

Requires the ``sdk:event-log`` API-key scope. High-level
:meth:`olira.OliraClient.upload_document` performs upload-url + PUT + commit;
there is no human confirm on this path.
"""

from __future__ import annotations

import hashlib
import mimetypes
import time
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from .exceptions import OliraError, ValidationError

if TYPE_CHECKING:
    from .http import HttpTransport


class DocumentLogType(StrEnum):
    UNSTRUCTURED_REPORT = "unstructured_report"
    CLINICAL_NOTE = "clinical_note"


class DocumentStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    OCR_RUNNING = "ocr_running"
    OCR_COMPLETE = "ocr_complete"
    OCR_FAILED = "ocr_failed"
    LOG_EMITTED = "log_emitted"

    @property
    def is_terminal(self) -> bool:
        return self in (DocumentStatus.LOG_EMITTED, DocumentStatus.OCR_FAILED)


class DocumentResource(BaseModel):
    document_id: str
    status: DocumentStatus
    filename: str
    patient_id: str
    log_type: str
    document_type: str | None = None
    note_type: str | None = None
    s3_uri: str | None = None
    event_log_id: str | None = None
    error: str | None = None
    ocr_page_count: int | None = None
    ocr_confidence: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DocumentHandle:
    """Poll/wait handle for a document OCR job."""

    def __init__(self, doc: DocumentResource, fetch: Callable[[str], DocumentResource]):
        self._doc = doc
        self._fetch = fetch

    @property
    def document_id(self) -> str:
        return self._doc.document_id

    @property
    def document(self) -> DocumentResource:
        return self._doc

    def poll(self) -> DocumentResource:
        self._doc = self._fetch(self._doc.document_id)
        return self._doc

    def wait(self, *, timeout_s: float = 600.0, poll_interval_s: float = 2.0) -> DocumentResource:
        deadline = time.monotonic() + timeout_s
        while True:
            doc = self.poll()
            if doc.status.is_terminal:
                return doc
            if time.monotonic() >= deadline:
                raise OliraError(f"Timed out waiting for document {doc.document_id} (status={doc.status.value})")
            time.sleep(poll_interval_s)


def upload_document_via_transport(
    transport: HttpTransport,
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
) -> DocumentHandle:
    """Upload-url → PUT → commit. Returns a pollable handle."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"Document file not found: {file_path}")
    blob = file_path.read_bytes()
    if not blob:
        raise ValidationError("Document file is empty")
    sha = hashlib.sha256(blob).hexdigest()
    resolved_ct = content_type or mimetypes.guess_type(file_path.name)[0] or "application/pdf"
    lt = DocumentLogType(log_type)

    body: dict[str, Any] = {
        "patient_id": patient_id,
        "content_type": resolved_ct,
        "content_sha256": sha,
        "size_bytes": len(blob),
        "filename": file_path.name,
        "log_type": lt.value,
        "timestamp": timestamp.isoformat(),
        "idempotency_key": idempotency_key,
    }
    if lt == DocumentLogType.UNSTRUCTURED_REPORT:
        if not document_type:
            raise ValidationError("document_type is required for unstructured_report")
        body["document_type"] = document_type
        if source is not None:
            body["source"] = source
    else:
        if not note_type:
            raise ValidationError("note_type is required for clinical_note")
        if source is None:
            raise ValidationError("source is required for clinical_note")
        body["note_type"] = note_type
        body["source"] = source

    upload = transport.get_document_upload_url(body)
    transport.put_presigned(
        upload["upload_url"],
        blob,
        headers={"Content-Type": resolved_ct},
    )
    transport.commit_document(upload["document_id"])
    doc = transport.get_document(upload["document_id"])
    return DocumentHandle(doc, fetch=transport.get_document)
