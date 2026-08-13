"""Tests for outbound-actions destination/delivery management on OliraClient / AsyncOliraClient.

Verifies each client method delegates to the right transport call with the
correct path args + body, including the digest_schedule presence-sensitivity
contract (explicit null to clear vs. omitted to leave unchanged) and the
cursor/params passthrough for delivery listing.
"""

import pytest

from olira import (
    ActionTrigger,
    AsyncOliraClient,
    DigestSchedule,
    EmailDestinationConfig,
    OliraClient,
    OliraEnv,
    WebhookDestinationConfig,
)


def _destination_dict(**over) -> dict:
    base = {
        "id": "dest_1",
        "project_id": None,
        "destination_type": "webhook",
        "status": "active",
        "description": None,
        "subscribed_event_types": ["patient.state.changed"],
        "config": {
            "destination_type": "webhook",
            "url": "https://hooks.example.com/olira",
            "api_version": "2026-08-01",
        },
        "signing_secret_last4": "wxlA",
        "rate_limit_per_minute": 600,
        "digest_schedule": None,
        "consecutive_failures": 0,
        "failure_streak_started_at": None,
        "auto_disabled_at": None,
        "rotated_at": None,
        "signing_secret": None,
    }
    base.update(over)
    return base


def _delivery_dict(**over) -> dict:
    base = {
        "id": "del_1",
        "project_id": None,
        "destination_id": "dest_1",
        "destination_type": "webhook",
        "event_type": "patient.state.changed",
        "event_id": "evt_1",
        "status": "delivered",
        "attempts": [],
        "next_attempt_at": None,
        "first_attempted_at": None,
        "delivered_at": "2026-08-12T09:14:05Z",
        "dead_lettered_at": None,
        "last_error": None,
        "redelivery_of": None,
        "requested_by": "dispatcher",
        "batched_into": None,
        "payload": None,
    }
    base.update(over)
    return base


class RecordingTransport:
    """Records the last actions call so tests can assert delegation."""

    def __init__(self):
        self.calls: list[tuple] = []

    def create_action_destination(self, body):
        self.calls.append(("create", body))
        from olira import ActionDestination

        return ActionDestination.model_validate(_destination_dict(signing_secret="whsec_abc123"))

    def list_action_destinations(self):
        self.calls.append(("list_destinations",))
        from olira import ActionDestinationListResult

        return ActionDestinationListResult.model_validate({"data": [_destination_dict()], "total": 1})

    def get_action_destination(self, destination_id):
        self.calls.append(("get_destination", destination_id))
        from olira import ActionDestination

        return ActionDestination.model_validate(_destination_dict(id=destination_id))

    def update_action_destination(self, destination_id, body):
        self.calls.append(("update", destination_id, body))
        from olira import ActionDestination

        return ActionDestination.model_validate(_destination_dict(id=destination_id))

    def delete_action_destination(self, destination_id):
        self.calls.append(("delete", destination_id))
        from olira import ActionDestinationDeleteResult

        return ActionDestinationDeleteResult.model_validate(
            {"message": "Destination disabled", "dead_lettered_deliveries": 2}
        )

    def rotate_action_destination_secret(self, destination_id):
        self.calls.append(("rotate", destination_id))
        from olira import ActionDestination

        return ActionDestination.model_validate(_destination_dict(id=destination_id, signing_secret="whsec_new456"))

    def list_action_deliveries(self, params):
        self.calls.append(("list_deliveries", params))
        from olira import ActionDeliveryListResult

        return ActionDeliveryListResult.model_validate({"data": [_delivery_dict()], "next_cursor": None})

    def get_action_delivery(self, delivery_id):
        self.calls.append(("get_delivery", delivery_id))
        from olira import ActionDelivery

        return ActionDelivery.model_validate(_delivery_dict(id=delivery_id, payload={"id": "del_1"}))

    def redeliver_action_delivery(self, delivery_id):
        self.calls.append(("redeliver", delivery_id))
        from olira import ActionDelivery

        return ActionDelivery.model_validate(_delivery_dict(id="del_2", status="pending", redelivery_of=delivery_id))

    def close(self):
        pass


def _sync_client() -> tuple[OliraClient, RecordingTransport]:
    client = OliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    transport = RecordingTransport()
    client._transport = transport
    client._worker = None
    return client, transport


def test_create_action_destination_delegates_full_body():
    client, t = _sync_client()
    dest = client.create_action_destination(
        config=WebhookDestinationConfig(url="https://hooks.example.com/olira"),
        subscribed_triggers=["patient.state.changed", "log.no_state_change"],
        description="Acme webhook",
        static_headers={"X-Api-Key": "secret"},
        rate_limit_per_minute=600,
        digest_schedule=DigestSchedule(
            time_of_day="09:00", timezone="America/New_York", triggers=["patient.state.changed"]
        ),
    )
    assert dest.signing_secret == "whsec_abc123"
    assert dest.subscribed_triggers == ["patient.state.changed"]  # from the (unrelated) recorded response fixture
    assert t.calls[-1] == (
        "create",
        {
            "config": {
                "destination_type": "webhook",
                "url": "https://hooks.example.com/olira",
                "api_version": "2026-08-01",
            },
            "subscribed_event_types": ["patient.state.changed", "log.no_state_change"],
            "description": "Acme webhook",
            "static_headers": {"X-Api-Key": "secret"},
            "rate_limit_per_minute": 600,
            "digest_schedule": {
                "time_of_day": "09:00",
                "timezone": "America/New_York",
                "event_types": ["patient.state.changed"],
            },
        },
    )
    client.close()


def test_create_action_destination_omits_unset_optionals():
    client, t = _sync_client()
    client.create_action_destination(config=WebhookDestinationConfig(url="https://hooks.example.com/olira"))
    assert t.calls[-1] == (
        "create",
        {
            "config": {
                "destination_type": "webhook",
                "url": "https://hooks.example.com/olira",
                "api_version": "2026-08-01",
            }
        },
    )
    client.close()


def test_create_action_destination_accepts_email_config():
    client, t = _sync_client()
    client.create_action_destination(config=EmailDestinationConfig(to_email="ops@acme.example"))
    assert t.calls[-1] == (
        "create",
        {"config": {"destination_type": "email", "to_email": "ops@acme.example"}},
    )
    client.close()


def test_create_action_destination_accepts_dict_config():
    """A raw dict config (e.g. for a destination type not yet modeled) passes through unmodified."""
    client, t = _sync_client()
    raw_config = {"destination_type": "slack", "channel_id": "C123"}
    client.create_action_destination(config=raw_config)
    assert t.calls[-1] == ("create", {"config": raw_config})
    client.close()


def test_create_action_destination_accepts_action_trigger_enum():
    """ActionTrigger members serialize identically to their plain-string values."""
    client, t = _sync_client()
    client.create_action_destination(
        config=WebhookDestinationConfig(url="https://hooks.example.com/olira"),
        subscribed_triggers=[ActionTrigger.PATIENT_STATE_CHANGED, ActionTrigger.INGESTION_FAILED],
    )
    body = t.calls[-1][1]
    assert body["subscribed_event_types"] == ["patient.state.changed", "ingestion.failed"]
    assert all(isinstance(v, str) for v in body["subscribed_event_types"])
    client.close()


def test_update_action_destination_sends_only_supplied_fields():
    client, t = _sync_client()
    client.update_action_destination(destination_id="dest_1", status="disabled")
    assert t.calls[-1] == ("update", "dest_1", {"status": "disabled"})
    client.close()


def test_update_action_destination_clear_digest_schedule_sends_explicit_null():
    client, t = _sync_client()
    client.update_action_destination(destination_id="dest_1", clear_digest_schedule=True)
    assert t.calls[-1] == ("update", "dest_1", {"digest_schedule": None})
    client.close()


def test_update_action_destination_omitted_digest_schedule_key_absent():
    client, t = _sync_client()
    client.update_action_destination(destination_id="dest_1", description="new desc")
    _, _, body = t.calls[-1]
    assert "digest_schedule" not in body
    client.close()


def test_update_action_destination_rejects_digest_schedule_and_clear_flag_together():
    client, _ = _sync_client()
    with pytest.raises(ValueError, match="not both"):
        client.update_action_destination(
            destination_id="dest_1",
            digest_schedule=DigestSchedule(time_of_day="09:00"),
            clear_digest_schedule=True,
        )
    client.close()


def test_update_action_destination_rejects_raw_dict_for_digest_schedule():
    """A raw dict silently misinterprets triggers/event_types; must raise, not forward it."""
    client, _ = _sync_client()
    with pytest.raises(TypeError, match="not a dict"):
        client.update_action_destination(
            destination_id="dest_1",
            digest_schedule={"triggers": ["patient.state.changed"]},  # type: ignore[arg-type]
        )
    client.close()


def test_create_action_destination_rejects_raw_dict_for_digest_schedule():
    client, _ = _sync_client()
    with pytest.raises(TypeError, match="not a dict"):
        client.create_action_destination(
            config=WebhookDestinationConfig(url="https://hooks.example.com/olira"),
            digest_schedule={"time_of_day": "09:00", "triggers": ["patient.state.changed"]},  # type: ignore[arg-type]
        )
    client.close()


def test_get_delete_rotate_action_destination_delegate():
    client, t = _sync_client()
    dest = client.get_action_destination(destination_id="dest_1")
    assert dest.id == "dest_1"
    assert t.calls[-1] == ("get_destination", "dest_1")

    result = client.delete_action_destination(destination_id="dest_1")
    assert result.dead_lettered_deliveries == 2
    assert t.calls[-1] == ("delete", "dest_1")

    rotated = client.rotate_action_destination_secret(destination_id="dest_1")
    assert rotated.signing_secret == "whsec_new456"
    assert t.calls[-1] == ("rotate", "dest_1")
    client.close()


def test_list_action_destinations_delegates():
    client, t = _sync_client()
    result = client.list_action_destinations()
    assert result.total == 1
    assert t.calls[-1] == ("list_destinations",)
    client.close()


def test_list_action_deliveries_params_passthrough_and_omission():
    client, t = _sync_client()
    client.list_action_deliveries(destination_id="dest_1", status="delivered", cursor="abc", limit=10)
    assert t.calls[-1] == (
        "list_deliveries",
        {"destination_id": "dest_1", "status": "delivered", "cursor": "abc", "limit": 10},
    )

    client.list_action_deliveries()
    assert t.calls[-1] == ("list_deliveries", {})
    client.close()


def test_get_and_redeliver_action_delivery_delegate():
    client, t = _sync_client()
    delivery = client.get_action_delivery(delivery_id="del_1")
    assert delivery.payload == {"id": "del_1"}
    assert delivery.trigger == "patient.state.changed"
    assert t.calls[-1] == ("get_delivery", "del_1")

    redelivered = client.redeliver_action_delivery(delivery_id="del_1")
    assert redelivered.redelivery_of == "del_1"
    assert t.calls[-1] == ("redeliver", "del_1")
    client.close()


class AsyncRecordingTransport:
    """Awaitable counterpart to RecordingTransport for the async client."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def create_action_destination(self, body):
        self.calls.append(("create", body))
        from olira import ActionDestination

        return ActionDestination.model_validate(_destination_dict(signing_secret="whsec_abc123"))

    async def list_action_destinations(self):
        self.calls.append(("list_destinations",))
        from olira import ActionDestinationListResult

        return ActionDestinationListResult.model_validate({"data": [_destination_dict()], "total": 1})

    async def get_action_destination(self, destination_id):
        self.calls.append(("get_destination", destination_id))
        from olira import ActionDestination

        return ActionDestination.model_validate(_destination_dict(id=destination_id))

    async def update_action_destination(self, destination_id, body):
        self.calls.append(("update", destination_id, body))
        from olira import ActionDestination

        return ActionDestination.model_validate(_destination_dict(id=destination_id))

    async def delete_action_destination(self, destination_id):
        self.calls.append(("delete", destination_id))
        from olira import ActionDestinationDeleteResult

        return ActionDestinationDeleteResult.model_validate(
            {"message": "Destination disabled", "dead_lettered_deliveries": 0}
        )

    async def rotate_action_destination_secret(self, destination_id):
        self.calls.append(("rotate", destination_id))
        from olira import ActionDestination

        return ActionDestination.model_validate(_destination_dict(id=destination_id, signing_secret="whsec_new456"))

    async def list_action_deliveries(self, params):
        self.calls.append(("list_deliveries", params))
        from olira import ActionDeliveryListResult

        return ActionDeliveryListResult.model_validate({"data": [_delivery_dict()], "next_cursor": "cur_2"})

    async def get_action_delivery(self, delivery_id):
        self.calls.append(("get_delivery", delivery_id))
        from olira import ActionDelivery

        return ActionDelivery.model_validate(_delivery_dict(id=delivery_id))

    async def redeliver_action_delivery(self, delivery_id):
        self.calls.append(("redeliver", delivery_id))
        from olira import ActionDelivery

        return ActionDelivery.model_validate(_delivery_dict(id="del_2", redelivery_of=delivery_id))

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_async_action_methods_delegate():
    client = AsyncOliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT)
    transport = AsyncRecordingTransport()
    client._transport = transport

    dest = await client.create_action_destination(
        config=WebhookDestinationConfig(url="https://hooks.example.com/olira")
    )
    assert dest.signing_secret == "whsec_abc123"

    listed = await client.list_action_destinations()
    assert listed.total == 1

    fetched = await client.get_action_destination(destination_id="dest_1")
    assert fetched.id == "dest_1"

    await client.update_action_destination(destination_id="dest_1", clear_digest_schedule=True)
    assert transport.calls[-1] == ("update", "dest_1", {"digest_schedule": None})

    deleted = await client.delete_action_destination(destination_id="dest_1")
    assert deleted.message == "Destination disabled"

    rotated = await client.rotate_action_destination_secret(destination_id="dest_1")
    assert rotated.signing_secret == "whsec_new456"

    deliveries = await client.list_action_deliveries(status="delivered")
    assert deliveries.next_cursor == "cur_2"

    delivery = await client.get_action_delivery(delivery_id="del_1")
    assert delivery.id == "del_1"

    redelivered = await client.redeliver_action_delivery(delivery_id="del_1")
    assert redelivered.redelivery_of == "del_1"

    await client.aclose()
