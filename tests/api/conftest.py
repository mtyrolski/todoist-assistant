"""Shared fixtures for API tests."""

from collections.abc import Iterator

from fastapi.testclient import TestClient
import pytest

import todoist.web.api as web_api


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    with TestClient(web_api.app) as client:
        yield client
