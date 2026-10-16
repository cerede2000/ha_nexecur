"""Config flow for NEXECUR."""

from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    NexecurApi,
    NexecurAuthenticationError,
    NexecurConnectionError,
    NexecurError,
)
from .const import CONF_DEVICE_ID, CONF_PIN, CONF_SITE_ID, CONF_SITE_NAME, DOMAIN


class NexecurConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NEXECUR."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure one NEXECUR site."""
        errors: dict[str, str] = {}
        if user_input is not None:
            site_id = str(user_input[CONF_SITE_ID]).strip()
            pin = str(user_input[CONF_PIN])
            if not site_id.isdigit():
                errors[CONF_SITE_ID] = "invalid_site_id"
            else:
                await self.async_set_unique_id(site_id)
                self._abort_if_unique_id_configured()
                device_id = f"home-assistant-{uuid.uuid4()}"
                try:
                    site_info = await _async_validate_credentials(
                        self.hass, site_id, pin, device_id
                    )
                except NexecurAuthenticationError:
                    errors["base"] = "invalid_auth"
                except NexecurConnectionError:
                    errors["base"] = "cannot_connect"
                except NexecurError:
                    errors["base"] = "unknown"
                else:
                    site_name = _site_name(site_info, site_id)
                    return self.async_create_entry(
                        title=site_name,
                        data={
                            CONF_SITE_ID: site_id,
                            CONF_PIN: pin,
                            CONF_DEVICE_ID: device_id,
                            CONF_SITE_NAME: site_name,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for and validate a replacement PIN."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            pin = str(user_input[CONF_PIN])
            try:
                await _async_validate_credentials(
                    self.hass,
                    str(entry.data[CONF_SITE_ID]),
                    pin,
                    str(entry.data[CONF_DEVICE_ID]),
                )
            except NexecurAuthenticationError:
                errors["base"] = "invalid_auth"
            except NexecurConnectionError:
                errors["base"] = "cannot_connect"
            except NexecurError:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PIN: pin},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PIN): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    )
                }
            ),
            errors=errors,
        )


def _credentials_schema(user_input: dict[str, Any] | None) -> vol.Schema:
    """Build the credentials form."""
    defaults = user_input or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_SITE_ID, default=defaults.get(CONF_SITE_ID, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                    autocomplete="username",
                )
            ),
            vol.Required(CONF_PIN): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.PASSWORD,
                    autocomplete="current-password",
                )
            ),
        }
    )


async def _async_validate_credentials(
    hass: Any, site_id: str, pin: str, device_id: str
) -> dict[str, Any]:
    """Authenticate and make one status read."""
    api = NexecurApi(async_get_clientsession(hass), site_id, pin, device_id)
    site_info = await api.async_authenticate()
    await api.async_get_panel_status()
    return site_info


def _site_name(site_info: dict[str, Any], site_id: str) -> str:
    """Return the configured site name."""
    raw_name = site_info.get("nom")
    if raw_name is not None and (name := str(raw_name).strip()):
        return name
    return f"NEXECUR {site_id}"
