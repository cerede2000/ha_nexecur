"""Alarm control panel platform for NEXECUR."""

from __future__ import annotations

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NexecurConfigEntry
from .api import NexecurError
from .const import (
    CONF_SITE_ID,
    DOMAIN,
    INTEGRATION_VERSION,
    PANEL_ARMED_AWAY,
    PANEL_ARMED_PARTIAL_1,
    PANEL_ARMED_PARTIAL_2,
    PANEL_ARMING,
    PANEL_CAMERA_DETECTION,
    PANEL_CONNECTED,
    PANEL_DISARMED,
    PANEL_DISCONNECTED,
    PANEL_TRIGGERED,
    PANEL_TRIGGERED_RESTORED,
)
from .coordinator import NexecurCoordinator

STATE_MAP = {
    PANEL_DISARMED: AlarmControlPanelState.DISARMED,
    PANEL_ARMED_AWAY: AlarmControlPanelState.ARMED_AWAY,
    PANEL_ARMED_PARTIAL_1: AlarmControlPanelState.ARMED_HOME,
    PANEL_ARMED_PARTIAL_2: AlarmControlPanelState.ARMED_NIGHT,
    PANEL_ARMING: AlarmControlPanelState.ARMING,
    PANEL_TRIGGERED: AlarmControlPanelState.TRIGGERED,
    PANEL_TRIGGERED_RESTORED: AlarmControlPanelState.DISARMED,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NexecurConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the alarm entity."""
    async_add_entities([NexecurAlarm(entry)])


class NexecurAlarm(CoordinatorEntity[NexecurCoordinator], AlarmControlPanelEntity):
    """Representation of a NEXECUR alarm site."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_code_arm_required = False
    def __init__(self, entry: NexecurConfigEntry) -> None:
        runtime = entry.runtime_data
        super().__init__(runtime.coordinator)
        self._api = runtime.api
        site_id = str(entry.data[CONF_SITE_ID])
        site_name = _site_name(runtime.api.site_info, site_id)
        self._attr_unique_id = f"{site_id}_alarm"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, site_id)},
            manufacturer="NEXECUR",
            model="Cloud alarm panel",
            name=site_name,
            sw_version=INTEGRATION_VERSION,
        )
        features = AlarmControlPanelEntityFeature.ARM_AWAY
        if _value_is_enabled(runtime.api.site_info.get("panel_sp1", 1)):
            features |= AlarmControlPanelEntityFeature.ARM_HOME
        if _value_is_enabled(runtime.api.site_info.get("panel_sp2", 1)):
            features |= AlarmControlPanelEntityFeature.ARM_NIGHT
        self._attr_supported_features = features

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the current alarm state."""
        if self.coordinator.data is None:
            return None
        return STATE_MAP.get(self.coordinator.data.get("panel_status"))

    @property
    def available(self) -> bool:
        """Return whether the cloud and the physical panel are available."""
        if not super().available or self.coordinator.data is None:
            return False
        return self.coordinator.data.get("panel_status") != PANEL_DISCONNECTED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose useful non-sensitive NEXECUR details."""
        data = self.coordinator.data or {}
        panel_status = data.get("panel_status")
        attributes: dict[str, Any] = {
            "integration_version": INTEGRATION_VERSION,
            "nexecur_panel_status": panel_status,
            "partial_1_name": self._api.site_info.get("panel_sp1_nom", "Partiel 1"),
            "partial_2_name": self._api.site_info.get("panel_sp2_nom", "Partiel 2"),
        }
        if panel_status == PANEL_CONNECTED:
            attributes["nexecur_event"] = "panel_connected"
        elif panel_status == PANEL_CAMERA_DETECTION:
            attributes["nexecur_event"] = "camera_detection"
        elif panel_status == PANEL_TRIGGERED_RESTORED:
            attributes["nexecur_event"] = "intrusion_restored"
        return attributes

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Disarm the alarm."""
        await self._async_set_status(PANEL_DISARMED)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Arm the whole site."""
        await self._async_set_status(PANEL_ARMED_AWAY)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Arm partial mode 1."""
        await self._async_set_status(PANEL_ARMED_PARTIAL_1)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Arm partial mode 2."""
        await self._async_set_status(PANEL_ARMED_PARTIAL_2)

    async def _async_set_status(self, status: int) -> None:
        """Run a command and publish its confirmed final state."""
        try:
            data = await self._api.async_set_panel_status(status)
        except NexecurError as err:
            raise HomeAssistantError(str(err)) from err
        self.coordinator.async_set_updated_data(data)


def _site_name(site_info: dict[str, Any], site_id: str) -> str:
    """Return a clean name for the site."""
    raw_name = site_info.get("nom")
    if raw_name is not None and (name := str(raw_name).strip()):
        return name
    return f"NEXECUR {site_id}"


def _value_is_enabled(value: Any) -> bool:
    """Interpret a loosely typed NEXECUR capability value."""
    return str(value).strip().lower() not in {"0", "false", "no", "none", ""}
