"""Data coordinator for NEXECUR."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NexecurApi, NexecurAuthenticationError, NexecurError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class NexecurCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the current NEXECUR alarm state."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: NexecurApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            always_update=False,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_panel_status()
        except NexecurAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NexecurError as err:
            raise UpdateFailed(str(err)) from err
