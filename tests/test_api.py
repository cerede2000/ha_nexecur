"""Reproducible authentication tests; no NEXECUR account is used."""

import base64
import hashlib
import json
import logging

import aiohttp
import pytest

from custom_components.nexecur.api import (
    NexecurAccountLockedError,
    NexecurApi,
    NexecurAuthenticationError,
    NexecurConnectionError,
    NexecurHTTPError,
    NexecurUnavailableError,
)
from custom_components.nexecur.const import API_BASE_URL

SALT = {"status": 0, "salt": "c2FsdA=="}
SITE = {"status": 0, "token": "synthetic-token", "nom": "Synthetic site"}


@pytest.mark.parametrize("status", [0, 10])
async def test_authentication_protocol_unchanged(responses, status):
    """Keep UTF-16LE PIN, SHA1/SHA256, headers, device ID and cached session."""
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload={**SITE, "status": status})
    async with aiohttp.ClientSession() as session:
        api = NexecurApi(session, "001234", "0123é", "synthetic-device")
        info = await api.async_authenticate()
        assert await api.async_authenticate() is info
    requests = [call for calls in responses.requests.values() for call in calls]
    assert len(requests) == 2
    assert json.loads(requests[0].kwargs["data"]) == {"id_site": 1234}
    material = b"salt" + "0123é".encode("utf-16le")
    assert json.loads(requests[1].kwargs["data"]) == {
        "id_site": 1234,
        "pin": base64.b64encode(hashlib.sha1(material).digest()).decode(),
        "password": base64.b64encode(hashlib.sha256(material).digest()).decode(),
        "partage": "1",
        "id_device": "synthetic-device",
    }
    assert requests[1].kwargs["headers"] == {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Auth-Token": "",
    }


@pytest.mark.parametrize(
    ("service", "payload", "error"),
    [
        ("salt", {"status": 0}, NexecurConnectionError),
        ("salt", {"status": 0, "salt": ""}, NexecurConnectionError),
        ("salt", {"status": 0, "salt": 123}, NexecurConnectionError),
        ("salt", {"status": 0, "salt": "%%%"}, NexecurConnectionError),
        ("salt", {"status": 7}, NexecurUnavailableError),
        ("salt", {"status": 99}, NexecurUnavailableError),
        ("salt", {"status": 2}, NexecurUnavailableError),
        ("salt", {}, NexecurConnectionError),
        ("salt", {"status": []}, NexecurConnectionError),
        ("salt", {"status": False, "salt": "c2FsdA=="}, NexecurConnectionError),
        ("site", {}, NexecurConnectionError),
        ("site", {"status": "0"}, NexecurConnectionError),
        ("site", {"status": {}}, NexecurConnectionError),
        ("site", {"status": 0}, NexecurConnectionError),
        ("site", {"status": 0, "token": []}, NexecurConnectionError),
        ("site", {"status": 7}, NexecurAccountLockedError),
        ("site", {"status": 2}, NexecurAuthenticationError),
        ("site", {"status": 3}, NexecurAuthenticationError),
        ("site", {"status": 4}, NexecurAuthenticationError),
        ("site", {"status": 99}, NexecurUnavailableError),
    ],
)
async def test_auth_error_classification(responses, service, payload, error):
    if service == "site":
        responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + service, payload=payload)
    async with aiohttp.ClientSession() as session:
        api = NexecurApi(session, "1234", "synthetic-pin", "device")
        with pytest.raises(error):
            await api.async_authenticate()


@pytest.mark.parametrize("status", [2, 3, 4])
async def test_session_renewed_once(responses, status):
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload=SITE)
    responses.post(API_BASE_URL + "panel-status", payload={"status": status})
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload={**SITE, "token": "new-token"})
    responses.post(API_BASE_URL + "panel-status", payload={"status": status})
    async with aiohttp.ClientSession() as session:
        api = NexecurApi(session, "1234", "synthetic-pin", "device")
        with pytest.raises(NexecurUnavailableError):
            await api.async_get_panel_status()
        assert api._token is None
    calls = [
        call
        for (method, url), calls in responses.requests.items()
        if str(url).endswith("panel-status")
        for call in calls
    ]
    assert len(calls) == 2
    assert calls[0].kwargs["headers"]["X-Auth-Token"] == "synthetic-token"
    assert calls[1].kwargs["headers"]["X-Auth-Token"] == "new-token"


async def test_failed_forced_auth_clears_token(responses):
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload=SITE)
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload={"status": 7})
    async with aiohttp.ClientSession() as session:
        api = NexecurApi(session, "1234", "pin", "device")
        await api.async_authenticate()
        with pytest.raises(NexecurAccountLockedError):
            await api.async_authenticate(force=True)
        assert api._token is None


@pytest.mark.parametrize(
    "response",
    [
        {"status": 503, "body": "synthetic-secret"},
        {"body": "not json synthetic-secret"},
        {"payload": []},
        {"exception": aiohttp.ClientConnectionError("synthetic-secret")},
        {"exception": TimeoutError()},
    ],
)
async def test_transport_errors_and_secret_safety(responses, caplog, response):
    caplog.set_level(logging.DEBUG, logger="custom_components.nexecur")
    responses.post(API_BASE_URL + "salt", **response)
    async with aiohttp.ClientSession() as session:
        api = NexecurApi(session, "1234", "synthetic-secret", "device")
        with pytest.raises(NexecurConnectionError) as caught:
            await api.async_authenticate()
    assert "synthetic-secret" not in str(caught.value)
    assert "synthetic-secret" not in caplog.text
    if response.get("status") == 503:
        assert isinstance(caught.value, NexecurHTTPError)
        assert caught.value.status == 503


async def test_safe_diagnostics(responses, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.nexecur")
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload=SITE)
    responses.post(
        API_BASE_URL + "panel-status", payload={"status": 0, "panel_status": 1}
    )
    async with aiohttp.ClientSession() as session:
        api = NexecurApi(session, "987654321", "synthetic-pin", "synthetic-device")
        assert (await api.async_get_panel_status())["panel_status"] == 1
    for secret in (
        "987654321",
        "synthetic-pin",
        "synthetic-device",
        "synthetic-token",
        "Synthetic site",
        SALT["salt"],
    ):
        assert secret not in caplog.text
    for service in ("salt", "site", "panel-status"):
        assert f"NEXECUR {service}: HTTP 200" in caplog.text
        assert f"NEXECUR {service}: service status 0" in caplog.text


async def test_session_renewal_succeeds(responses):
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload=SITE)
    responses.post(API_BASE_URL + "panel-status", payload={"status": 2})
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload={**SITE, "token": "renewed"})
    responses.post(
        API_BASE_URL + "panel-status", payload={"status": 0, "panel_status": 1}
    )
    async with aiohttp.ClientSession() as session:
        api = NexecurApi(session, "1234", "pin", "device")
        assert await api.async_get_panel_status() == {"status": 0, "panel_status": 1}
        assert api._token == "renewed"
