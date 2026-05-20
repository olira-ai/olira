"""Tests for patient_id PII guard and payload size."""

import pytest

from olira import ValidationError
from olira.models import _LogWire, _validate_patient_id


def test_patient_id_empty_raises():
    with pytest.raises(ValidationError, match="empty or whitespace"):
        _validate_patient_id("")
    with pytest.raises(ValidationError, match="empty or whitespace"):
        _validate_patient_id("   ")


def test_patient_id_email_raises():
    with pytest.raises(ValidationError, match="email"):
        _validate_patient_id("user@example.com")


def test_patient_id_ssn_raises():
    with pytest.raises(ValidationError, match="SSN"):
        _validate_patient_id("123-45-6789")


def test_patient_id_phone_raises():
    with pytest.raises(ValidationError, match="phone"):
        _validate_patient_id("5551234567")


def test_patient_id_pseudo_ok():
    assert _validate_patient_id("p_abc123") == "p_abc123"
    assert _validate_patient_id("subject_xyz") == "subject_xyz"


def test_log_wire_validates_patient_id():
    with pytest.raises(ValidationError):
        _LogWire(
            log_type="user_login",
            patient_id="user@example.com",
            context={"environment": "production", "service": "", "sdk_version": "0.1.0", "sdk_language": "python"},
        )
