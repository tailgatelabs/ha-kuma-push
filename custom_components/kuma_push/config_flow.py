"""Config flow for Uptime Kuma Push."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from yarl import URL

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    KumaPushAuthError,
    KumaPushConnectionError,
    KumaPushRejectedError,
    access_headers,
    async_push,
    normalize_push_url,
)
from .const import (
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_INTERVAL,
    CONF_PUSH_URL,
    DEFAULT_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_INTERVAL,
    MIN_INTERVAL,
)

EXAMPLE_URL = "https://kuma.example.com/api/push/abc123"
SECTION_ACCESS = "cloudflare_access"

INTERVAL_SELECTOR = vol.All(
    NumberSelector(
        NumberSelectorConfig(
            min=MIN_INTERVAL,
            max=MAX_INTERVAL,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="s",
        )
    ),
    vol.Coerce(int),
)

ACCESS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ACCESS_CLIENT_ID): TextSelector(),
        vol.Optional(CONF_ACCESS_CLIENT_SECRET): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


def _parse_access(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Return the Access credentials to store, or {} if none were given.

    Raises ValueError if only one of the client ID and secret is set.
    """
    client_id = user_input.get(CONF_ACCESS_CLIENT_ID, "").strip()
    client_secret = user_input.get(CONF_ACCESS_CLIENT_SECRET, "").strip()
    if bool(client_id) != bool(client_secret):
        raise ValueError("Client ID and secret must be set together")
    if not client_id:
        return {}
    return {CONF_ACCESS_CLIENT_ID: client_id, CONF_ACCESS_CLIENT_SECRET: client_secret}


class KumaPushConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Uptime Kuma Push."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the push URL and interval, then verify with a test push."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = normalize_push_url(user_input[CONF_PUSH_URL])
            except ValueError:
                errors[CONF_PUSH_URL] = "invalid_url"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                try:
                    access = _parse_access(user_input.get(SECTION_ACCESS, {}))
                except ValueError:
                    errors["base"] = "incomplete_access"
                else:
                    errors = await self._async_test_push(url, access)
                    if not errors:
                        return self.async_create_entry(
                            title=URL(url).host or url,
                            data={CONF_PUSH_URL: url, **access},
                            options={CONF_INTERVAL: user_input[CONF_INTERVAL]},
                        )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_PUSH_URL): TextSelector(
                            TextSelectorConfig(type=TextSelectorType.URL)
                        ),
                        vol.Required(
                            CONF_INTERVAL, default=DEFAULT_INTERVAL
                        ): INTERVAL_SELECTOR,
                        vol.Required(SECTION_ACCESS): section(
                            ACCESS_SCHEMA, {"collapsed": True}
                        ),
                    }
                ),
                user_input,
            ),
            errors=errors,
            description_placeholders={"example_url": EXAMPLE_URL},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle rejected Cloudflare Access credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new Cloudflare Access credentials."""
        return await self._async_step_access(
            "reauth_confirm", self._get_reauth_entry(), user_input
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change or remove the Cloudflare Access credentials."""
        return await self._async_step_access(
            "reconfigure", self._get_reconfigure_entry(), user_input
        )

    async def _async_step_access(
        self,
        step_id: str,
        entry: ConfigEntry,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Update an entry's Access credentials after a successful test push."""
        url: str = entry.data[CONF_PUSH_URL]
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                access = _parse_access(user_input)
            except ValueError:
                errors["base"] = "incomplete_access"
            else:
                errors = await self._async_test_push(url, access)
                if not errors:
                    return self.async_update_reload_and_abort(
                        entry, data={CONF_PUSH_URL: url, **access}
                    )
        else:
            # Prefill the client ID only; the secret is never shown back.
            user_input = {
                key: value
                for key, value in entry.data.items()
                if key == CONF_ACCESS_CLIENT_ID
            }

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(ACCESS_SCHEMA, user_input),
            errors=errors,
            description_placeholders={"host": entry.title},
        )

    async def _async_test_push(
        self, url: str, access: Mapping[str, str]
    ) -> dict[str, str]:
        """Send a test push and return form errors, empty on success."""
        try:
            await async_push(
                async_get_clientsession(self.hass),
                url,
                headers=access_headers(
                    access.get(CONF_ACCESS_CLIENT_ID),
                    access.get(CONF_ACCESS_CLIENT_SECRET),
                ),
            )
        except KumaPushAuthError as err:
            LOGGER.debug("Test push denied: %s", err)
            return {"base": "invalid_auth"}
        except KumaPushConnectionError as err:
            LOGGER.debug("Test push failed: %s", err)
            return {"base": "cannot_connect"}
        except KumaPushRejectedError as err:
            LOGGER.debug("Test push rejected: %s", err)
            return {"base": "rejected"}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KumaPushOptionsFlow:
        """Return the options flow."""
        return KumaPushOptionsFlow()


class KumaPushOptionsFlow(OptionsFlowWithReload):
    """Change the push interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_INTERVAL): INTERVAL_SELECTOR}),
                self.config_entry.options,
            ),
        )
