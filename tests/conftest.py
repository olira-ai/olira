"""Pytest fixtures and configuration."""

import pytest


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level client so tests don't leak state."""
    import olira

    old = olira._client
    olira._client = None
    yield
    olira._client = old
