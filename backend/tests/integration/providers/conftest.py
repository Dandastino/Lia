"""Fixtures for the REST connector driver tests: every HTTP call is mocked with ``responses``."""
from __future__ import annotations

import asyncio

import pytest
import responses


@pytest.fixture
def rsps():
    """A strict ``responses`` mock: any unregistered outbound request raises ConnectionError."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def run():
    """Run a coroutine to completion (pytest-asyncio is intentionally not used)."""
    return asyncio.run
