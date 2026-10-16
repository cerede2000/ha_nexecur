"""Constants for the NEXECUR integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "nexecur"
PLATFORMS = ["alarm_control_panel"]

CONF_SITE_ID = "site_id"
CONF_PIN = "pin"
CONF_DEVICE_ID = "device_id"
CONF_SITE_NAME = "site_name"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
API_BASE_URL = "https://monnexecur-prd.nexecur.fr/webservices/"

PANEL_DISARMED = 0
PANEL_ARMED_AWAY = 1
PANEL_ARMED_PARTIAL_1 = 2
PANEL_ARMED_PARTIAL_2 = 3
PANEL_ARMING = 4
PANEL_TRIGGERED = 5
PANEL_TRIGGERED_RESTORED = 6
PANEL_DISCONNECTED = 10
PANEL_CONNECTED = 11
PANEL_CAMERA_DETECTION = 12

SESSION_ERROR_STATUSES = {2, 3, 4}
