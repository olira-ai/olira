"""Local JSONL validation for historical data ingestion.

Validates structure and field presence entirely offline — no network calls.
Use before ``create_ingestion_job()`` to catch problems immediately rather
than waiting for server-side Stage 1 to reject the file.

What is checked locally:
  - Each line is valid JSON
  - ``type`` is ``"patient"`` or ``"log"``
  - Patient anchor rule: at least one identifying field present
  - Log required fields: ``event_type``, ``patient_id``, ``timestamp``
  - ``event_type`` is a known platform type (via OliraLogType)
  - ``timestamp`` is parseable ISO 8601
  - ``patient_id`` in each log resolves to a patient defined anywhere in the file (order-agnostic)
    (within-file check only; existing org patients are not checked)

What requires a network call and is NOT checked locally:
  - Whether ``patient_id`` refers to an existing org patient not in this file
  - Whether ``event_type`` payload matches the server-side JSON Schema
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import IngestionRowError, IngestRecord, OliraLogType

if TYPE_CHECKING:
    pass

_VALID_EVENT_TYPES: frozenset[str] = frozenset(t.value for t in OliraLogType)

_ANCHOR_FIELDS = ("external_identifiers", "email", "phone_number", "first_name", "last_name", "date_of_birth")


def _has_anchor(data: dict[str, Any]) -> bool:
    if data.get("external_identifiers"):
        return True
    return any(bool(data.get(f)) for f in _ANCHOR_FIELDS[1:])


def _parse_iso(value: str) -> bool:
    """Return True if value is a parseable ISO 8601 datetime string."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            datetime.strptime(value.rstrip("Z") + "+00:00" if value.endswith("Z") else value, fmt)
            return True
        except ValueError:
            pass
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


_DEFAULT_MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB


def validate_ingestion_file(
    path: str | Path,
    max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
) -> list[IngestionRowError]:
    """Validate a JSONL ingestion file locally before uploading.

    Returns a list of :class:`IngestionRowError` entries — one per problem found.
    An empty list means the file passed all local checks.

    Does **not** make any network calls. Patient resolution against existing org
    patients requires a server call and is not checked here.

    Patient and log records may appear in any order in the file; validation collects
    all patient identifiers before checking log ``patient_id`` references.

    Raises ``FileNotFoundError`` if the path does not exist.
    Raises ``OSError`` if the file cannot be read.

    Example::

        errors = olira.validate_ingestion_file("patients_and_logs.jsonl")
        if errors:
            for e in errors:
                print(f"Line {e.line}: [{e.code}] {e.message}")
        else:
            job = olira.create_ingestion_job(file="patients_and_logs.jsonl")
    """
    errors: list[IngestionRowError] = []

    file_size = Path(path).stat().st_size
    if file_size > max_file_bytes:
        return [
            IngestionRowError(
                line=0,
                code="file_too_large",
                message=(
                    f"File is {file_size / (1024 * 1024):.1f} MB, exceeds the "
                    f"{max_file_bytes // (1024 * 1024)} MB limit. "
                    "Split into smaller batches and submit as separate jobs."
                ),
            )
        ]

    known_patient_ids: set[str] = set()
    parsed: list[tuple[int, str, dict[str, Any]]] = []

    with open(path, encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(
                    IngestionRowError(line=line_num, code="invalid_json", message=f"Line is not valid JSON: {exc.msg}")
                )
                continue
            if not isinstance(row, dict):
                errors.append(
                    IngestionRowError(line=line_num, code="invalid_json", message="Each line must be a JSON object")
                )
                continue

            record_type = row.get("type")
            data = row.get("data")

            if record_type not in ("patient", "log"):
                errors.append(
                    IngestionRowError(
                        line=line_num,
                        code="unknown_record_type",
                        message=f"type must be 'patient' or 'log', got {record_type!r}",
                    )
                )
                continue
            if not isinstance(data, dict):
                errors.append(
                    IngestionRowError(line=line_num, code="missing_data", message="Record must have a 'data' object")
                )
                continue

            if record_type == "patient":
                if not _has_anchor(data):
                    errors.append(
                        IngestionRowError(
                            line=line_num,
                            code="missing_anchor",
                            message=(
                                "Patient record must have at least one of: "
                                "external_identifiers, email, phone_number, first_name, last_name, date_of_birth"
                            ),
                        )
                    )
                for ext in data.get("external_identifiers") or []:
                    if isinstance(ext, dict) and ext.get("value"):
                        known_patient_ids.add(str(ext["value"]))

            parsed.append((line_num, record_type, data))

    for line_num, record_type, data in parsed:
        if record_type != "log":
            continue

        if not data.get("event_type"):
            errors.append(
                IngestionRowError(
                    line=line_num, code="missing_event_type", message="Log record must have an 'event_type' field"
                )
            )
        else:
            et = data["event_type"]
            if et not in _VALID_EVENT_TYPES:
                suggestion = _suggest(et)
                msg = f"Unknown event_type {et!r}"
                if suggestion:
                    msg += f" — did you mean {suggestion!r}?"
                errors.append(IngestionRowError(line=line_num, code="unknown_event_type", message=msg))

        if not data.get("patient_id"):
            errors.append(
                IngestionRowError(
                    line=line_num, code="missing_patient_id", message="Log record must have a 'patient_id' field"
                )
            )
        else:
            pid = str(data["patient_id"])
            if pid not in known_patient_ids and not _looks_like_uuid(pid):
                errors.append(
                    IngestionRowError(
                        line=line_num,
                        code="patient_id_not_in_file",
                        message=(
                            f"patient_id {pid!r} not found in any patient record in this file. "
                            "If the patient was created separately (e.g. via create_patients_batch) "
                            "it will resolve server-side and is not an error."
                        ),
                    )
                )

        if not data.get("timestamp"):
            errors.append(
                IngestionRowError(
                    line=line_num, code="missing_timestamp", message="Log record must have a 'timestamp' field"
                )
            )
        elif not _parse_iso(str(data["timestamp"])):
            errors.append(
                IngestionRowError(
                    line=line_num,
                    code="invalid_timestamp",
                    message=(
                        f"timestamp {data['timestamp']!r} is not a valid ISO 8601 datetime. "
                        "Use format: '2025-01-15T09:00:00Z'"
                    ),
                )
            )

    return errors


def validate_ingestion_records(records: list[IngestRecord]) -> list[IngestionRowError]:
    """Validate a list of :class:`IngestRecord` objects locally before submitting inline.

    Same checks as :func:`validate_ingestion_file` but operates on already-parsed records.
    Patient and log records may appear in any order. Line numbers are 1-indexed positions
    in the ``records`` list.

    Returns an empty list if all records pass.
    """
    errors: list[IngestionRowError] = []

    known_patient_ids: set[str] = set()
    for i, record in enumerate(records, start=1):
        if record.type == "patient":
            data = record.data
            if not _has_anchor(data):
                errors.append(
                    IngestionRowError(
                        line=i,
                        code="missing_anchor",
                        message=(
                            "Patient record must have at least one of: "
                            "external_identifiers, email, phone_number, first_name, last_name, date_of_birth"
                        ),
                    )
                )
            for ext in data.get("external_identifiers") or []:
                if isinstance(ext, dict) and ext.get("value"):
                    known_patient_ids.add(str(ext["value"]))
        elif record.type not in ("patient", "log"):
            errors.append(
                IngestionRowError(
                    line=i,
                    code="unknown_record_type",
                    message=f"type must be 'patient' or 'log', got {record.type!r}",
                )
            )

    for i, record in enumerate(records, start=1):
        data = record.data
        record_type = record.type

        if record_type not in ("patient", "log"):
            continue

        if record_type == "patient":
            continue

        if record_type == "log":
            et = data.get("event_type", "")
            if not et:
                errors.append(
                    IngestionRowError(
                        line=i, code="missing_event_type", message="Log record must have an 'event_type' field"
                    )
                )
            elif et not in _VALID_EVENT_TYPES:
                suggestion = _suggest(et)
                msg = f"Unknown event_type {et!r}"
                if suggestion:
                    msg += f" — did you mean {suggestion!r}?"
                errors.append(IngestionRowError(line=i, code="unknown_event_type", message=msg))

            if not data.get("patient_id"):
                errors.append(
                    IngestionRowError(
                        line=i, code="missing_patient_id", message="Log record must have a 'patient_id' field"
                    )
                )
            else:
                pid = str(data["patient_id"])
                if pid not in known_patient_ids and not _looks_like_uuid(pid):
                    errors.append(
                        IngestionRowError(
                            line=i,
                            code="patient_id_not_in_file",
                            message=(
                                f"patient_id {pid!r} not found in any patient record in this list. "
                                "If the patient was created separately (e.g. via create_patients_batch) "
                                "it will resolve server-side and is not an error."
                            ),
                        )
                    )

            if not data.get("timestamp"):
                errors.append(
                    IngestionRowError(
                        line=i, code="missing_timestamp", message="Log record must have a 'timestamp' field"
                    )
                )
            elif not _parse_iso(str(data["timestamp"])):
                errors.append(
                    IngestionRowError(
                        line=i,
                        code="invalid_timestamp",
                        message=f"timestamp {data['timestamp']!r} is not a valid ISO 8601 datetime",
                    )
                )

    return errors


import re as _re  # noqa: E402

_UUID_RE = _re.compile(
    r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$",
    _re.IGNORECASE,
)


def _looks_like_uuid(value: str) -> bool:
    """Return True if value looks like an Olira ObjectId or UUID (24-char hex or UUID4)."""
    if _re.match(r"^[0-9a-f]{24}$", value, _re.IGNORECASE):
        return True
    return bool(_UUID_RE.match(value))


def _suggest(event_type: str) -> str | None:
    """Return the closest known event type if edit distance is small, else None."""
    best: str | None = None
    best_dist = 3  # only suggest if within 3 edits
    for known in _VALID_EVENT_TYPES:
        d = _levenshtein(event_type, known)
        if d < best_dist:
            best_dist = d
            best = known
    return best


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance — used for typo suggestions only."""
    if len(a) > len(b):
        a, b = b, a
    row = list(range(len(a) + 1))
    for j, cb in enumerate(b, 1):
        prev = j
        for i, ca in enumerate(a, 1):
            curr = row[i - 1] if ca == cb else 1 + min(row[i - 1], row[i], prev)
            row[i - 1] = prev
            prev = curr
        row[len(a)] = prev
    return row[len(a)]
