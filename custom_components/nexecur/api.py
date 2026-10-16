"""Asynchronous client for the private Mon NEXECUR mobile API."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
import hashlib
import json
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import API_BASE_URL, SESSION_ERROR_STATUSES

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
COMMAND_TIMEOUT = 65
COMMAND_POLL_INTERVAL = 5

ACTION_ERRORS = {
    101: "another action is already running",
    102: "unknown alarm panel",
    103: "alarm panel is disconnected",
    104: "invalid code",
    105: "the alarm panel rejected the request",
    106: "internal alarm panel error",
}


class NexecurError(Exception):
    """Base NEXECUR error."""


class NexecurConnectionError(NexecurError):
    """The NEXECUR service could not be reached or returned invalid data."""


class NexecurAuthenticationError(NexecurError):
    """The credentials were rejected."""


class NexecurUnavailableError(NexecurError):
    """The site or panel is temporarily unavailable."""


class NexecurCommandError(NexecurError):
    """The alarm command was rejected or could not be confirmed."""


class NexecurHTTPError(NexecurConnectionError):
    """A request returned a non-success HTTP status."""

    def __init__(self, service: str, status: int, detail: str) -> None:
        self.service = service
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status} from {service}: {detail}")


class NexecurApi:
    """Client for a single NEXECUR site."""

    def __init__(
        self,
        session: ClientSession,
        site_id: str,
        pin: str,
        device_id: str,
    ) -> None:
        self._session = session
        self.site_id = str(site_id)
        self._pin = pin
        self._device_id = device_id
        self._token: str | None = None
        self._command_lock = asyncio.Lock()
        self.site_info: dict[str, Any] = {}

    async def async_authenticate(self, *, force: bool = False) -> dict[str, Any]:
        """Authenticate and return the site description."""
        if self._token is not None and not force:
            return self.site_info

        salt_response = await self._async_post("salt", {"id_site": int(self.site_id)})
        if salt_response.get("status") != 0 or not salt_response.get("salt"):
            raise NexecurAuthenticationError("Unable to retrieve the authentication salt")

        try:
            salt = base64.b64decode(salt_response["salt"], validate=True)
        except (TypeError, ValueError) as err:
            raise NexecurConnectionError("NEXECUR returned an invalid authentication salt") from err

        material = salt + self._pin.encode("utf-16le")
        payload = {
            "id_site": int(self.site_id),
            "pin": base64.b64encode(hashlib.sha1(material).digest()).decode("ascii"),
            "password": base64.b64encode(hashlib.sha256(material).digest()).decode("ascii"),
            "partage": "1",
            "id_device": self._device_id,
        }
        response = await self._async_post("site", payload)
        status = response.get("status")
        if status not in (0, 10):
            if status == 7:
                raise NexecurAuthenticationError("The account is temporarily locked")
            raise NexecurAuthenticationError("The connection code or PIN was rejected")

        token = response.get("token")
        if not token:
            raise NexecurConnectionError("NEXECUR authenticated but returned no session token")

        self._token = str(token)
        self.site_info = response
        return response

    async def async_get_panel_status(self) -> dict[str, Any]:
        """Return the current panel status, renewing the session once if necessary."""
        await self.async_authenticate()
        response = await self._async_post("panel-status", {}, token=self._token)
        if response.get("status") in SESSION_ERROR_STATUSES:
            await self.async_authenticate(force=True)
            response = await self._async_post("panel-status", {}, token=self._token)
        self._raise_service_error(response, command=False)
        return response

    async def async_set_panel_status(self, requested_status: int) -> dict[str, Any]:
        """Send one alarm command and wait for the requested status.

        NEXECUR sometimes returns HTTP 500 after having accepted a command. A
        mutating request must therefore never be retried. We only read the state
        until the requested state is observed.
        """
        async with self._command_lock:
            return await self._async_set_panel_status_locked(requested_status)

    async def _async_set_panel_status_locked(
        self, requested_status: int
    ) -> dict[str, Any]:
        """Execute one serialized panel command."""
        if requested_status not in (0, 1, 2, 3):
            raise ValueError(f"Unsupported panel status: {requested_status}")

        # Obtain a fresh token before the command. This avoids retrying a
        # mutating operation when an old token expires during the request.
        await self.async_authenticate(force=True)
        self._ensure_command_available(requested_status)

        command_was_uncertain = False
        try:
            response = await self._async_post(
                "panel-status", {"status": requested_status}, token=self._token
            )
        except NexecurHTTPError as err:
            if err.status != 500:
                raise NexecurCommandError(str(err)) from err
            command_was_uncertain = True
            response = {}
            _LOGGER.warning(
                "NEXECUR returned HTTP 500 after an alarm command; the command "
                "will not be resent and its result will be checked by reading status"
            )

        if not command_was_uncertain:
            self._raise_service_error(response, command=True)
            if response.get("pending") == 1:
                await self._async_wait_until_not_pending()

        return await self._async_wait_for_status(requested_status)

    def _ensure_command_available(self, requested_status: int) -> None:
        """Validate capabilities returned during authentication."""
        if self.site_info.get("status") == 10:
            raise NexecurUnavailableError("This shared access is outside its allowed time window")
        if not _value_is_enabled(self.site_info.get("panel_available", 1)):
            raise NexecurUnavailableError("This account cannot control the alarm panel")
        if requested_status == 2 and not _value_is_enabled(self.site_info.get("panel_sp1", 1)):
            raise NexecurUnavailableError("Partial mode 1 is not enabled for this site")
        if requested_status == 3 and not _value_is_enabled(self.site_info.get("panel_sp2", 1)):
            raise NexecurUnavailableError("Partial mode 2 is not enabled for this site")

    async def _async_wait_until_not_pending(self) -> None:
        """Wait until NEXECUR reports that its command queue is free."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + COMMAND_TIMEOUT
        while loop.time() < deadline:
            await asyncio.sleep(COMMAND_POLL_INTERVAL)
            check = await self._async_post("check-panel-status", {}, token=self._token)
            self._raise_service_error(check, command=True)
            if check.get("still_pending") == 0:
                return
        raise NexecurCommandError("The alarm panel did not finish the command in time")

    async def _async_wait_for_status(self, requested_status: int) -> dict[str, Any]:
        """Read until the panel reaches the requested state."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + COMMAND_TIMEOUT
        last_status: Any = None
        last_error: Exception | None = None

        while loop.time() < deadline:
            await asyncio.sleep(COMMAND_POLL_INTERVAL)
            try:
                result = await self.async_get_panel_status()
            except (NexecurConnectionError, NexecurUnavailableError) as err:
                last_error = err
                continue
            last_status = result.get("panel_status")
            if last_status == requested_status:
                return result

        detail = f"; last panel status was {last_status}" if last_status is not None else ""
        if last_error is not None:
            detail += f"; last read failed: {last_error}"
        raise NexecurCommandError(
            "The command may have been executed, but its final state could not be confirmed"
            + detail
        )

    def _raise_service_error(self, response: Mapping[str, Any], *, command: bool) -> None:
        """Raise a typed exception for an API-level status."""
        status = response.get("status")
        if status == 0:
            return
        if status in SESSION_ERROR_STATUSES:
            self._token = None
            raise NexecurAuthenticationError("The NEXECUR session is invalid or expired")
        if command:
            message = ACTION_ERRORS.get(status, "the alarm command was rejected")
            raise NexecurCommandError(f"{message} (service status {status})")
        raise NexecurUnavailableError(f"Unable to read alarm status (service status {status})")

    async def _async_post(
        self,
        service: str,
        body: Mapping[str, Any],
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        """POST JSON using the content type expected by the mobile API."""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Auth-Token": token or "",
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.post(
                    f"{API_BASE_URL}{service}",
                    data=json.dumps(body, separators=(",", ":")),
                    headers=headers,
                )
                return await self._async_decode_response(service, response)
        except TimeoutError as err:
            raise NexecurConnectionError(f"Timeout while calling {service}") from err
        except ClientError as err:
            raise NexecurConnectionError(f"Connection failed while calling {service}: {err}") from err

    @staticmethod
    async def _async_decode_response(
        service: str, response: ClientResponse
    ) -> dict[str, Any]:
        """Decode one response and retain HTTP errors for command safety."""
        raw = await response.text()
        if response.status < 200 or response.status >= 300:
            raise NexecurHTTPError(service, response.status, raw[:300])
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as err:
            raise NexecurConnectionError(f"Invalid response from {service}") from err
        if not isinstance(decoded, dict):
            raise NexecurConnectionError(f"Unexpected response from {service}")
        return decoded


def _value_is_enabled(value: Any) -> bool:
    """Return whether a loosely typed API capability is enabled."""
    return str(value).strip().lower() not in {"0", "false", "no", "none", ""}
