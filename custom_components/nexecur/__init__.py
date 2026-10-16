"""NEXECUR integration for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NexecurApi
from .const import CONF_DEVICE_ID, CONF_PIN, CONF_SITE_ID
from .coordinator import NexecurCoordinator

PLATFORMS = [Platform.ALARM_CONTROL_PANEL]


@dataclass
class NexecurRuntimeData:
    """Objects used by one config entry."""

    api: NexecurApi
    coordinator: NexecurCoordinator


NexecurConfigEntry = ConfigEntry[NexecurRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: NexecurConfigEntry) -> bool:
    """Set up NEXECUR from a config entry."""
    api = NexecurApi(
        async_get_clientsession(hass),
        str(entry.data[CONF_SITE_ID]),
        str(entry.data[CONF_PIN]),
        str(entry.data[CONF_DEVICE_ID]),
    )
    coordinator = NexecurCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = NexecurRuntimeData(api=api, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NexecurConfigEntry) -> bool:
    """Unload a NEXECUR config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
