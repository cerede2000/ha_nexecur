"""Real Home Assistant fixtures, with only the HTTP boundary simulated."""

import json
from collections import defaultdict, deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Allow loading this custom integration in Home Assistant."""


class ApiResponses:
    """Queue synthetic responses at ClientSession.post without a live service."""

    def __init__(self):
        self.pending = deque()
        self.requests = defaultdict(list)

    def post(self, url, **response):
        self.pending.append((url, response))

    async def request(self, url, **kwargs):
        assert self.pending, f"Unexpected API request to {url}"
        expected_url, response = self.pending.popleft()
        assert str(url) == expected_url
        self.requests[("POST", str(url))].append(SimpleNamespace(kwargs=kwargs))
        if "exception" in response:
            raise response["exception"]
        body = (
            json.dumps(response["payload"])
            if "payload" in response
            else response.get("body", "")
        )
        return SimpleNamespace(
            status=response.get("status", 200),
            text=AsyncMock(return_value=body),
            release=Mock(),
        )


@pytest.fixture
def responses():
    """Simulate all POST calls; sockets are also disabled by pytest-socket."""
    mocked = ApiResponses()
    with patch("aiohttp.ClientSession.post", side_effect=mocked.request):
        yield mocked
    assert not mocked.pending, "Expected API requests were not made"
