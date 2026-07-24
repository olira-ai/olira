"""Tests for project (workspace) management on OliraClient / AsyncOliraClient.

Verifies each client method delegates to the right transport call with the
correct path args + body, and that `project=` at init selects the workspace.
"""

import pytest

from olira import AsyncOliraClient, OliraClient, OliraEnv


def _project_dict(slug: str = "dev-sandbox", **over) -> dict:
    base = {
        "id": "proj_1",
        "name": "Dev Sandbox",
        "slug": slug,
        "description": None,
        "environment": "dev",
        "status": "active",
        "is_default": False,
        "created_at": "2026-01-01T00:00:00Z",
        "deprecated_at": None,
    }
    base.update(over)
    return base


class RecordingTransport:
    """Records the last project call so tests can assert delegation."""

    def __init__(self):
        self.calls: list[tuple] = []

    # sync + async share these names; async client awaits the return value,
    # so return already-resolved values and expose async wrappers below.
    def create_project(self, body):
        self.calls.append(("create", body))
        from olira import Project

        return Project.model_validate(_project_dict())

    def duplicate_project(self, project, body):
        self.calls.append(("duplicate", project, body))
        from olira import Project

        return Project.model_validate(_project_dict(slug="prod"))

    def update_project(self, project, body):
        self.calls.append(("update", project, body))
        from olira import Project

        return Project.model_validate(_project_dict(name=body.get("name", "Dev Sandbox")))

    def deprecate_project(self, project):
        self.calls.append(("deprecate", project))
        from olira import Project

        return Project.model_validate(_project_dict(status="deprecated"))

    def restore_project(self, project):
        self.calls.append(("restore", project))
        from olira import Project

        return Project.model_validate(_project_dict(status="active"))

    def delete_project(self, project):
        self.calls.append(("delete", project))

    def close(self):
        pass


def _sync_client() -> tuple[OliraClient, RecordingTransport]:
    client = OliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT, async_flush=False)
    transport = RecordingTransport()
    client._transport = transport
    client._worker = None
    return client, transport


def test_create_project_delegates():
    client, t = _sync_client()
    p = client.create_project(name="Dev Sandbox", slug="dev-sandbox", description="d", environment="dev")
    assert p.slug == "dev-sandbox"
    assert t.calls[-1] == (
        "create",
        {"name": "Dev Sandbox", "slug": "dev-sandbox", "description": "d", "environment": "dev"},
    )
    client.close()


def test_create_project_omits_slug_when_not_given():
    client, t = _sync_client()
    client.create_project(name="Dev Sandbox")
    # slug key absent so the server derives it from the name
    assert t.calls[-1] == ("create", {"name": "Dev Sandbox"})
    client.close()


def test_duplicate_project_delegates():
    client, t = _sync_client()
    p = client.duplicate_project(project="dev-sandbox", name="Prod", slug="prod", environment="prod")
    assert p.slug == "prod"
    assert t.calls[-1] == ("duplicate", "dev-sandbox", {"name": "Prod", "slug": "prod", "environment": "prod"})
    client.close()


def test_rename_project_sends_only_supplied_fields():
    client, t = _sync_client()
    client.rename_project(project="dev-sandbox", name="Renamed")
    assert t.calls[-1] == ("update", "dev-sandbox", {"name": "Renamed"})
    client.close()


def test_deprecate_restore_delete_delegate():
    client, t = _sync_client()
    assert client.deprecate_project(project="p").status == "deprecated"
    assert t.calls[-1] == ("deprecate", "p")
    assert client.restore_project(project="p").status == "active"
    assert t.calls[-1] == ("restore", "p")
    assert client.delete_project(project="p") is None
    assert t.calls[-1] == ("delete", "p")
    client.close()


def test_project_selected_at_init_sets_context():
    """`project=` flows into the per-request context used for the header/log context."""
    client = OliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT, project="dev-sandbox", async_flush=False)
    assert client._project == "dev-sandbox"
    assert client._context.get("project") == "dev-sandbox"
    client.close()


class AsyncRecordingTransport:
    """Awaitable counterpart to RecordingTransport for the async client."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def create_project(self, body):
        self.calls.append(("create", body))
        from olira import Project

        return Project.model_validate(_project_dict())

    async def duplicate_project(self, project, body):
        self.calls.append(("duplicate", project, body))
        from olira import Project

        return Project.model_validate(_project_dict(slug="prod"))

    async def update_project(self, project, body):
        self.calls.append(("update", project, body))
        from olira import Project

        return Project.model_validate(_project_dict())

    async def deprecate_project(self, project):
        self.calls.append(("deprecate", project))
        from olira import Project

        return Project.model_validate(_project_dict(status="deprecated"))

    async def restore_project(self, project):
        self.calls.append(("restore", project))
        from olira import Project

        return Project.model_validate(_project_dict(status="active"))

    async def delete_project(self, project):
        self.calls.append(("delete", project))

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_async_project_methods_delegate():
    client = AsyncOliraClient(api_key="key", environment=OliraEnv.DEVELOPMENT, project="dev-sandbox")
    transport = AsyncRecordingTransport()
    client._transport = transport

    p = await client.create_project(name="Dev Sandbox")
    assert p.slug == "dev-sandbox"
    dup = await client.duplicate_project(project="dev-sandbox", name="Prod")
    assert dup.slug == "prod"
    await client.rename_project(project="p", description="x")
    assert transport.calls[-1] == ("update", "p", {"description": "x"})
    await client.deprecate_project(project="p")
    await client.restore_project(project="p")
    assert await client.delete_project(project="p") is None
    assert client._project == "dev-sandbox"
    await client.aclose()
