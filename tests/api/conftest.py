# ruff: noqa: I001
"""Shared test fixtures for API endpoint tests."""
from __future__ import annotations

import pytest
from tests.support.app_harness import BaseAppRoutesTestCase


@pytest.fixture
def app_harness():
    """Provide BaseAppRoutesTestCase harness for API tests."""
    harness = BaseAppRoutesTestCase()
    harness.setUp()
    yield harness
    harness.tearDown()


@pytest.fixture
def app(app_harness):
    """Provide Flask test app."""
    return app_harness.app


@pytest.fixture
def client(app_harness):
    """Provide Flask test client."""
    return app_harness.client


@pytest.fixture
def create_conversation(app_harness):
    """Provide conversation creator helper."""
    return app_harness._create_conversation
