"""Exercise setup and reauthentication using the actual Home Assistant flows."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nexecur.api import (
    NexecurAccountLockedError,
    NexecurApi,
    NexecurAuthenticationError,
    NexecurUnavailableError,
)
from custom_components.nexecur.const import API_BASE_URL, DOMAIN
from custom_components.nexecur.coordinator import NexecurCoordinator

from .test_api import SALT, SITE


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="1234",
        data={
            "site_id": "1234",
            "pin": "old-pin",
            "device_id": "existing-device",
            "site_name": "Site",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize("reauth", [False, True])
@pytest.mark.parametrize(
    ("service", "payload", "expected"),
    [
        ("salt", {"status": 0}, "cannot_connect"),
        ("salt", {"status": 99}, "service_unavailable"),
        ("salt", {"status": 7}, "service_unavailable"),
        ("site", {"status": 7}, "account_locked"),
        ("site", {"status": 2}, "invalid_auth"),
        ("site", {}, "cannot_connect"),
        ("site", {"status": 99}, "service_unavailable"),
        ("panel-status", {"status": 103}, "service_unavailable"),
        ("panel-status", {}, "cannot_connect"),
    ],
)
async def test_flow_error(hass, responses, reauth, service, payload, expected):
    if service != "salt":
        responses.post(API_BASE_URL + "salt", payload=SALT)
    if service == "panel-status":
        responses.post(API_BASE_URL + "site", payload=SITE)
    responses.post(API_BASE_URL + service, payload=payload)
    if reauth:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id="1234",
            data={"site_id": "1234", "pin": "old-pin", "device_id": "existing-device"},
        )
        entry.add_to_hass(hass)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "new-pin"}
        )
        assert entry.data["pin"] == "old-pin"
    else:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={"site_id": "1234", "pin": "synthetic-pin"},
        )
        assert not hass.config_entries.async_entries(DOMAIN)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_form_and_local_validation(hass, responses):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert {str(key) for key in result["data_schema"].schema} == {"site_id", "pin"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"site_id": "abc", "pin": "pin"}
    )
    assert result["errors"] == {"site_id": "invalid_site_id"}
    assert not responses.requests


async def test_duplicate_site(hass, entry, responses):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"site_id": "1234", "pin": "pin"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert not responses.requests


@pytest.mark.parametrize("name", ["Named site", "", None])
async def test_successful_setup(hass, responses, name):
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload={**SITE, "nom": name})
    responses.post(
        API_BASE_URL + "panel-status", payload={"status": 0, "panel_status": 0}
    )
    with patch("custom_components.nexecur.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={"site_id": " 1234 ", "pin": "0123"},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == (name or "NEXECUR 1234")
    assert result["data"]["site_id"] == "1234"
    assert result["data"]["pin"] == "0123"
    assert result["data"]["device_id"].startswith("home-assistant-")


async def test_successful_reauth(hass, responses, entry):
    responses.post(API_BASE_URL + "salt", payload=SALT)
    responses.post(API_BASE_URL + "site", payload=SITE)
    responses.post(
        API_BASE_URL + "panel-status", payload={"status": 0, "panel_status": 0}
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    with patch.object(hass.config_entries, "async_reload", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "new-pin"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["pin"] == "new-pin"
    assert entry.data["device_id"] == "existing-device"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (NexecurAccountLockedError("locked"), UpdateFailed),
        (NexecurUnavailableError("unavailable"), UpdateFailed),
        (NexecurAuthenticationError("rejected"), ConfigEntryAuthFailed),
    ],
)
async def test_coordinator_reauth_only_for_auth_failure(hass, entry, error, expected):
    api = AsyncMock(spec=NexecurApi)
    api.async_get_panel_status.side_effect = error
    coordinator = NexecurCoordinator(hass, entry, api)
    with pytest.raises(expected):
        await coordinator._async_update_data()


@pytest.mark.parametrize("reauth", [False, True])
async def test_fresh_session_rejection_is_not_invalid_pin(hass, responses, reauth):
    for _ in range(2):
        responses.post(API_BASE_URL + "salt", payload=SALT)
        responses.post(API_BASE_URL + "site", payload=SITE)
        responses.post(API_BASE_URL + "panel-status", payload={"status": 2})
    if reauth:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id="1234",
            data={"site_id": "1234", "pin": "old", "device_id": "device"},
        )
        entry.add_to_hass(hass)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "new"}
        )
    else:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"site_id": "1234", "pin": "pin"}
        )
    assert result["errors"] == {"base": "service_unavailable"}
