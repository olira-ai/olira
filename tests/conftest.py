"""Pytest fixtures and configuration."""

import pytest


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level client so tests don't leak state."""
    from olira import _module_api

    old = _module_api._client
    _module_api._client = None
    yield
    _module_api._client = old
