"""Tests for ExternalIdentifier.integration_id round-trip and the
add/remove_patient_external_identifiers methods.
"""

import pytest

from olira import (
    AsyncOliraClient,
    ExternalIdentifier,
    ExternalIdentifierMatcher,
    ExternalIdentifierMutationResult,
    OliraClient,
    Patient,
    PatientListResult,
    UpdatePatientRequest,
    ValidationError,
)


def test_external_identifier_defaults_integration_id_to_none():
    ident = ExternalIdentifier(system="qurate", value="Q1")
    assert ident.integration_id is None


def test_external_identifier_round_trips_integration_id():
    raw = {"system": "epic", "value": "MRN1", "integration_id": "itg_1"}
    ident = ExternalIdentifier.model_validate(raw)
    assert ident.integration_id == "itg_1"
    assert ident.model_dump()["integration_id"] == "itg_1"


def test_get_patient_parses_integration_id_from_response():
    """The regression this ticket exists for: GET must not silently drop integration_id."""
    raw = {
        "id": "p1",
        "timezone": "UTC",
        "status": "active",
        "external_identifiers": [{"system": "epic", "value": "MRN1", "integration_id": "itg_1"}],
    }
    patient = Patient.model_validate(raw)
    assert patient.external_identifiers[0].integration_id == "itg_1"


def test_update_patient_request_omits_integration_id_when_unset():
    """exclude_none must drop integration_id from the wire body when the caller
    doesn't set it — omitting is how the server preserves a stored link."""
    req = UpdatePatientRequest(external_identifiers=[ExternalIdentifier(system="epic", value="MRN1")])
    body = req.model_dump(exclude_none=True)
    assert body["external_identifiers"] == [{"system": "epic", "value": "MRN1"}]


def test_update_patient_request_sends_integration_id_when_echoed():
    req = UpdatePatientRequest(
        external_identifiers=[ExternalIdentifier(system="epic", value="MRN1", integration_id="itg_1")]
    )
    body = req.model_dump(exclude_none=True)
    assert body["external_identifiers"] == [{"system": "epic", "value": "MRN1", "integration_id": "itg_1"}]


def test_update_patient_request_rejects_empty_external_identifiers_client_side():
    """Client-side fail-fast on the same empty-list case the server rejects with 422 —
    avoids a round trip for a request that can never succeed."""
    with pytest.raises(ValidationError, match="cannot be emptied"):
        UpdatePatientRequest(external_identifiers=[])


class _RecordingTransport:
    def __init__(self, result):
        self.calls: list[tuple] = []
        self._result = result

    def add_patient_external_identifiers(self, patient_id, body):
        self.calls.append(("add", patient_id, body))
        return self._result

    def remove_patient_external_identifiers(self, patient_id, body):
        self.calls.append(("remove", patient_id, body))
        return self._result

    def update_patient(self, patient_id, body):
        self.calls.append(("update", patient_id, body))
        return None

    def list_patients(self, params):
        self.calls.append(("list", params))
        return PatientListResult(patients=[], total=0, has_more=False)

    def close(self):
        pass


class _AsyncRecordingTransport:
    def __init__(self, result):
        self.calls: list[tuple] = []
        self._result = result

    async def add_patient_external_identifiers(self, patient_id, body):
        self.calls.append(("add", patient_id, body))
        return self._result

    async def remove_patient_external_identifiers(self, patient_id, body):
        self.calls.append(("remove", patient_id, body))
        return self._result

    async def update_patient(self, patient_id, body):
        self.calls.append(("update", patient_id, body))
        return None

    async def aclose(self):
        pass


def _mutation_result() -> ExternalIdentifierMutationResult:
    return ExternalIdentifierMutationResult(
        patient_id="p1",
        added=1,
        external_identifiers=[ExternalIdentifier(system="qurate", value="Q1")],
    )


def test_add_patient_external_identifiers_strips_integration_id_from_body():
    client = OliraClient(api_key="olira_test_key", async_flush=False)
    transport = _RecordingTransport(_mutation_result())
    client._transport = transport

    result = client.add_patient_external_identifiers(
        patient_id="p1",
        # Even if a caller passes an object plucked from a GET response with
        # integration_id set, it must never be sent — the endpoint rejects it.
        identifiers=[ExternalIdentifier(system="epic", value="MRN1", integration_id="itg_1")],
    )

    assert transport.calls == [("add", "p1", {"identifiers": [{"system": "epic", "value": "MRN1"}]})]
    assert result.added == 1
    client.close()


def test_external_identifier_matcher_rejects_value_without_system():
    with pytest.raises(ValidationError, match="value requires system"):
        ExternalIdentifierMatcher(value="MRN1")


def test_external_identifier_matcher_rejects_empty():
    with pytest.raises(ValidationError, match="specify at least one"):
        ExternalIdentifierMatcher()


def test_remove_patient_external_identifiers_sends_system_and_value_matcher():
    client = OliraClient(api_key="olira_test_key", async_flush=False)
    transport = _RecordingTransport(_mutation_result())
    client._transport = transport

    client.remove_patient_external_identifiers(
        patient_id="p1",
        identifiers=[ExternalIdentifierMatcher(system="epic", value="MRN1")],
    )

    assert transport.calls == [("remove", "p1", {"identifiers": [{"system": "epic", "value": "MRN1"}]})]
    client.close()


def test_remove_patient_external_identifiers_system_only_matcher():
    """A system-only matcher (no value) removes every identifier for that system — the
    request body must not send a value key at all."""
    client = OliraClient(api_key="olira_test_key", async_flush=False)
    transport = _RecordingTransport(_mutation_result())
    client._transport = transport

    client.remove_patient_external_identifiers(
        patient_id="p1",
        identifiers=[ExternalIdentifierMatcher(system="epic")],
    )

    assert transport.calls == [("remove", "p1", {"identifiers": [{"system": "epic"}]})]
    client.close()


def test_remove_patient_external_identifiers_integration_id_only_matcher():
    """An integration_id-only matcher removes every identifier for that integration
    instance, regardless of system or value."""
    client = OliraClient(api_key="olira_test_key", async_flush=False)
    transport = _RecordingTransport(_mutation_result())
    client._transport = transport

    client.remove_patient_external_identifiers(
        patient_id="p1",
        identifiers=[ExternalIdentifierMatcher(integration_id="itg_1")],
    )

    assert transport.calls == [("remove", "p1", {"identifiers": [{"integration_id": "itg_1"}]})]
    client.close()


@pytest.mark.asyncio
async def test_async_add_patient_external_identifiers_strips_integration_id():
    async with AsyncOliraClient(api_key="olira_test_key") as client:
        transport = _AsyncRecordingTransport(_mutation_result())
        client._transport = transport

        await client.add_patient_external_identifiers(
            patient_id="p1",
            identifiers=[ExternalIdentifier(system="epic", value="MRN1", integration_id="itg_1")],
        )

    assert transport.calls == [("add", "p1", {"identifiers": [{"system": "epic", "value": "MRN1"}]})]


@pytest.mark.asyncio
async def test_async_remove_patient_external_identifiers_strips_integration_id():
    async with AsyncOliraClient(api_key="olira_test_key") as client:
        transport = _AsyncRecordingTransport(_mutation_result())
        client._transport = transport

        await client.remove_patient_external_identifiers(
            patient_id="p1",
            identifiers=[ExternalIdentifierMatcher(system="epic", value="MRN1")],
        )

    assert transport.calls == [("remove", "p1", {"identifiers": [{"system": "epic", "value": "MRN1"}]})]


def test_list_patients_system_only_filter():
    client = OliraClient(api_key="olira_test_key", async_flush=False)
    transport = _RecordingTransport(None)
    client._transport = transport

    client.list_patients(external_system="epic")

    assert transport.calls == [("list", {"limit": 100, "offset": 0, "external_system": "epic"})]
    client.close()


def test_list_patients_integration_id_only_filter():
    client = OliraClient(api_key="olira_test_key", async_flush=False)
    transport = _RecordingTransport(None)
    client._transport = transport

    client.list_patients(integration_id="itg_1")

    assert transport.calls == [("list", {"limit": 100, "offset": 0, "integration_id": "itg_1"})]
    client.close()


def test_list_patients_system_and_value_filter():
    client = OliraClient(api_key="olira_test_key", async_flush=False)
    transport = _RecordingTransport(None)
    client._transport = transport

    client.list_patients(external_system="epic", external_value="MRN1")

    assert transport.calls == [
        ("list", {"limit": 100, "offset": 0, "external_system": "epic", "external_value": "MRN1"})
    ]
    client.close()
