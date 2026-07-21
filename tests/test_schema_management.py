"""Tests for the org schema/mapping management methods on OliraClient/AsyncOliraClient.

Follows the hand-rolled MockTransport convention used elsewhere in this suite
(test_client.py, test_async_client.py): swap a fake transport into the client and
assert on both the request shape it receives and the response it hands back.
"""

import pytest

from olira import (
    AsyncOliraClient,
    OliraClient,
    OliraEnv,
    SchemaActionResult,
    SchemaCheckResult,
    SchemaDetail,
    SchemaRegistrationResult,
    SchemaSummary,
)


class _MockTransport:
    """Records every schema-management call and returns a canned response."""

    def __init__(self):
        self.calls: list[tuple] = []

    def close(self):
        pass

    def register_schema(self, body):
        self.calls.append(("register_schema", body))
        return SchemaRegistrationResult(
            registration_id="reg_1",
            subtype=body["subtype"],
            target_version=1,
            submission_mode="assisted",
            status="pending_review",
        )

    def list_schemas(self):
        self.calls.append(("list_schemas",))
        return [SchemaSummary(subtype="widget_ping", status="pending", active_version=None, latest_version=1)]

    def get_schema(self, subtype):
        self.calls.append(("get_schema", subtype))
        return SchemaDetail(subtype=subtype, status="pending", active_version=None, versions=[])

    def check_schema(self, body):
        self.calls.append(("check_schema", body))
        return SchemaCheckResult(ok=True, results=[])

    def edit_schema(self, subtype, body):
        self.calls.append(("edit_schema", subtype, body))
        return SchemaRegistrationResult(
            registration_id="reg_2",
            subtype=subtype,
            target_version=2,
            submission_mode="assisted",
            status="pending_review",
        )

    def deprecate_schema(self, subtype, params):
        self.calls.append(("deprecate_schema", subtype, params))
        return SchemaActionResult(subtype=subtype, version=params.get("version", 1), status="deprecated")

    def activate_schema_version(self, subtype, version):
        self.calls.append(("activate_schema_version", subtype, version))
        return SchemaActionResult(subtype=subtype, version=version, status="active")


def _client_with_mock() -> tuple[OliraClient, _MockTransport]:
    client = OliraClient(api_key="olira_test_key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    transport = _MockTransport()
    client._transport = transport
    client._worker = None
    return client, transport


def test_register_schema_assisted_body_omits_unset_fields():
    client, transport = _client_with_mock()
    result = client.register_schema(subtype="widget_ping", description="a ping event")
    assert result.submission_mode == "assisted"
    _, body = transport.calls[0]
    assert body == {"subtype": "widget_ping", "description": "a ping event"}
    client.close()


def test_register_schema_full_spec_uses_payload_schema_wire_key():
    client, transport = _client_with_mock()
    schema = {"type": "object"}
    mapping = {"targets": []}
    client.register_schema(subtype="widget_pong", schema=schema, mapping=mapping, input_examples=[{"a": 1}])
    _, body = transport.calls[0]
    assert body["payload_schema"] == schema
    assert body["mapping"] == mapping
    assert body["input_examples"] == [{"a": 1}]
    assert "schema" not in body
    client.close()


def test_list_schemas_returns_parsed_summaries():
    client, transport = _client_with_mock()
    result = client.list_schemas()
    assert len(result) == 1
    assert result[0].subtype == "widget_ping"
    assert transport.calls == [("list_schemas",)]
    client.close()


def test_get_schema_passes_subtype_through():
    client, transport = _client_with_mock()
    detail = client.get_schema(subtype="widget_ping")
    assert detail.subtype == "widget_ping"
    assert transport.calls == [("get_schema", "widget_ping")]
    client.close()


def test_check_schema_inline_spec_uses_payload_schema_wire_key():
    client, transport = _client_with_mock()
    schema = {"type": "object"}
    mapping = {"targets": []}
    result = client.check_schema(examples=[{"a": 1}], schema=schema, mapping=mapping)
    assert result.ok is True
    _, body = transport.calls[0]
    assert body == {"examples": [{"a": 1}], "payload_schema": schema, "mapping": mapping}
    client.close()


def test_check_schema_by_subtype_omits_inline_fields():
    client, transport = _client_with_mock()
    client.check_schema(examples=[{"a": 1}], subtype="widget_ping", version=2)
    _, body = transport.calls[0]
    assert body == {"examples": [{"a": 1}], "subtype": "widget_ping", "version": 2}
    client.close()


def test_edit_schema_only_includes_provided_fields():
    client, transport = _client_with_mock()
    result = client.edit_schema(subtype="widget_ping", description="new desc")
    assert result.target_version == 2
    _, subtype, body = transport.calls[0]
    assert subtype == "widget_ping"
    assert body == {"description": "new desc"}
    client.close()


def test_deprecate_schema_without_version_sends_empty_params():
    client, transport = _client_with_mock()
    result = client.deprecate_schema(subtype="widget_ping")
    assert result.status == "deprecated"
    _, subtype, params = transport.calls[0]
    assert subtype == "widget_ping"
    assert params == {}
    client.close()


def test_deprecate_schema_with_version_includes_it():
    client, transport = _client_with_mock()
    client.deprecate_schema(subtype="widget_ping", version=1)
    _, _subtype, params = transport.calls[0]
    assert params == {"version": 1}
    client.close()


def test_activate_schema_version_passes_through():
    client, transport = _client_with_mock()
    result = client.activate_schema_version(subtype="widget_ping", version=2)
    assert result.status == "active"
    assert transport.calls == [("activate_schema_version", "widget_ping", 2)]
    client.close()


class _AsyncMockTransport:
    def __init__(self):
        self.calls: list[tuple] = []

    async def aclose(self):
        pass

    async def register_schema(self, body):
        self.calls.append(("register_schema", body))
        return SchemaRegistrationResult(
            registration_id="reg_1",
            subtype=body["subtype"],
            target_version=1,
            submission_mode="assisted",
            status="pending_review",
        )

    async def activate_schema_version(self, subtype, version):
        self.calls.append(("activate_schema_version", subtype, version))
        return SchemaActionResult(subtype=subtype, version=version, status="active")


@pytest.mark.asyncio
async def test_async_client_register_and_activate_schema():
    transport = _AsyncMockTransport()
    async with AsyncOliraClient(api_key="olira_test_key", environment=OliraEnv.DEVELOPMENT) as client:
        client._transport = transport
        registration = await client.register_schema(subtype="widget_ping", description="x")
        assert registration.submission_mode == "assisted"

        activated = await client.activate_schema_version(subtype="widget_ping", version=1)
        assert activated.status == "active"

    assert transport.calls[0] == ("register_schema", {"subtype": "widget_ping", "description": "x"})
    assert transport.calls[1] == ("activate_schema_version", "widget_ping", 1)
