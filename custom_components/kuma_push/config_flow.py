"""Config flow for Uptime Kuma Push."""

from __future__ import annotations

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
    KumaPushConnectionError,
    KumaPushRejectedError,
    async_push,
    normalize_push_url,
)
from .const import (
    CONF_INTERVAL,
    CONF_PUSH_URL,
    DEFAULT_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_INTERVAL,
    MIN_INTERVAL,
)

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
                    await async_push(async_get_clientsession(self.hass), url)
                except KumaPushConnectionError as err:
                    LOGGER.debug("Test push failed: %s", err)
                    errors["base"] = "cannot_connect"
                except KumaPushRejectedError as err:
                    LOGGER.debug("Test push rejected: %s", err)
                    errors["base"] = "rejected"
                else:
                    return self.async_create_entry(
                        title=URL(url).host or url,
                        data={CONF_PUSH_URL: url},
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
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

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
