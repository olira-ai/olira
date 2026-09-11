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

from pydantic import BaseModel, Field

from .exceptions import OliraError, ValidationError

if TYPE_CHECKING:
    from .http import HttpTransport


class DocumentLogType(StrEnum):
    UNSTRUCTURED_REPORT = "unstructured_report"
    CLINICAL_NOTE = "clinical_note"


class DocumentProcessingMode(StrEnum):
    """How a document's OCR text becomes event logs.

    ``single_document`` (default) emits one log for the whole file at the ``timestamp`` you
    supply. ``segmented_notes`` treats the file as a container spanning many encounters:
    you supply no timestamp, and one ``clinical_note`` log is emitted per detected visit
    entry, each dated from the document's own content.
    """

    SINGLE_DOCUMENT = "single_document"
    SEGMENTED_NOTES = "segmented_notes"


class DocumentStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    OCR_RUNNING = "ocr_running"
    OCR_COMPLETE = "ocr_complete"
    OCR_FAILED = "ocr_failed"
    LOG_EMITTED = "log_emitted"
    # segmented_notes only:
    SEGMENTING = "segmenting"
    LOGS_EMITTED = "logs_emitted"
    SEGMENTATION_FAILED = "segmentation_failed"

    @property
    def is_terminal(self) -> bool:
        return self in (
            DocumentStatus.LOG_EMITTED,
            DocumentStatus.LOGS_EMITTED,
            DocumentStatus.OCR_FAILED,
            DocumentStatus.SEGMENTATION_FAILED,
        )


class DocumentSegment(BaseModel):
    """One detected encounter entry in a ``segmented_notes`` document.

    ``status == "held"`` means the segment was detected but not emitted — ``hold_reason``
    says why (an unresolvable date, one outside ``date_hints``, an out-of-order date, or
    empty text).
    """

    index: int
    kind: str
    page_start: int
    page_end: int
    leaf: str | None = None
    date_text: str | None = None
    timestamp: str | None = None
    date_precision: str | None = None
    # True when the written two-digit year was impossible for the document's span and a year
    # the span admits was substituted instead (opt-in via date_hints["reconstruct_year"]).
    # The day and month are as written; only the year is inferred. `year_candidates` is how
    # many years fitted — anything above 1 means a tie-break chose.
    year_reconstructed: bool = False
    year_candidates: int = 0
    status: str
    hold_reason: str | None = None
    event_log_id: str | None = None


class DocumentResource(BaseModel):
    document_id: str
    status: DocumentStatus
    filename: str
    patient_id: str
    log_type: str
    document_type: str | None = None
    note_type: str | None = None
    processing_mode: str = DocumentProcessingMode.SINGLE_DOCUMENT.value
    s3_uri: str | None = None
    event_log_id: str | None = None
    event_log_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    ocr_page_count: int | None = None
    ocr_confidence: float | None = None
    ocr_method: str | None = None
    segments_detected: int | None = None
    segments_emitted: int | None = None
    segments_held: int | None = None
    segments_year_reconstructed: int | None = None
    unassigned_chars: int | None = None
    segments: list[DocumentSegment] = Field(default_factory=list)
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
    idempotency_key: str,
    timestamp: datetime | None = None,
    processing_mode: DocumentProcessingMode | str = DocumentProcessingMode.SINGLE_DOCUMENT,
    date_hints: dict[str, Any] | None = None,
    layout_hints: dict[str, Any] | None = None,
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
    mode = DocumentProcessingMode(processing_mode)

    if mode == DocumentProcessingMode.SINGLE_DOCUMENT:
        if timestamp is None:
            raise ValidationError("timestamp is required for processing_mode=single_document")
        if date_hints is not None or layout_hints is not None:
            raise ValidationError("date_hints / layout_hints only apply to processing_mode=segmented_notes")
    else:
        if timestamp is not None:
            raise ValidationError(
                "timestamp must be omitted for processing_mode=segmented_notes — each emitted "
                "note is dated from the document's own content"
            )
        if lt != DocumentLogType.CLINICAL_NOTE:
            raise ValidationError("processing_mode=segmented_notes requires log_type=clinical_note")

    body: dict[str, Any] = {
        "patient_id": patient_id,
        "content_type": resolved_ct,
        "content_sha256": sha,
        "size_bytes": len(blob),
        "filename": file_path.name,
        "log_type": lt.value,
        "processing_mode": mode.value,
        "idempotency_key": idempotency_key,
    }
    if timestamp is not None:
        body["timestamp"] = timestamp.isoformat()
    if date_hints is not None:
        body["date_hints"] = date_hints
    if layout_hints is not None:
        body["layout_hints"] = layout_hints
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
