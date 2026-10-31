"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.kuma_push.const import (
    CONF_ACCESS_CLIENT_ID,
    CONF_ACCESS_CLIENT_SECRET,
    CONF_INTERVAL,
    CONF_PUSH_URL,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import PUSH_URL, setup_integration

ACCESS = {CONF_ACCESS_CLIENT_ID: "id.access", CONF_ACCESS_CLIENT_SECRET: "secret"}
ACCESS_HEADERS = {
    "CF-Access-Client-Id": "id.access",
    "CF-Access-Client-Secret": "secret",
}


@pytest.mark.usefixtures("mock_setup_entry", "mock_kuma_ok")
async def test_user_flow(hass: HomeAssistant) -> None:
    """A valid URL creates an entry with the query string stripped."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PUSH_URL: f"{PUSH_URL}?status=up&msg=OK&ping=",
            CONF_INTERVAL: 30,
            "cloudflare_access": {},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "kuma.example.com"
    assert result["data"] == {CONF_PUSH_URL: PUSH_URL}
    assert result["options"] == {CONF_INTERVAL: 30}
    assert result["result"].unique_id == PUSH_URL


@pytest.mark.parametrize(
    ("kwargs", "errors"),
    [
        ({"exc": TimeoutError()}, {"base": "cannot_connect"}),
        ({"status": 404, "json": {"ok": False, "msg": "x"}}, {"base": "rejected"}),
        ({"status": 403}, {"base": "invalid_auth"}),
    ],
)
async def test_user_flow_push_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_setup_entry: AsyncMock,
    kwargs: dict,
    errors: dict[str, str],
) -> None:
    """Failed test pushes show an error and the flow can recover."""
    aioclient_mock.get(PUSH_URL, **kwargs)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    user_input = {
        CONF_PUSH_URL: PUSH_URL,
        CONF_INTERVAL: 60,
        "cloudflare_access": {},
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors

    aioclient_mock.clear_requests()
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_flow_invalid_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An invalid URL is rejected without a request."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PUSH_URL: "https://kuma.example.com/dashboard",
            CONF_INTERVAL: 60,
            "cloudflare_access": {},
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PUSH_URL: "invalid_url"}
    assert aioclient_mock.call_count == 0


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The same push URL cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PUSH_URL: f"{PUSH_URL}?status=up",
            CONF_INTERVAL: 60,
            "cloudflare_access": {},
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert aioclient_mock.call_count == 0


@pytest.mark.usefixtures("mock_kuma_ok")
async def test_options_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Changing the interval reloads the entry with the new interval."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_INTERVAL: 120}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_INTERVAL: 120}
    coordinator = mock_config_entry.runtime_data
    assert coordinator.update_interval.total_seconds() == 120


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_access(
    hass: HomeAssistant, mock_kuma_ok: AiohttpClientMocker
) -> None:
    """Access credentials are trimmed, stored and sent with the test push."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PUSH_URL: PUSH_URL,
            CONF_INTERVAL: 60,
            "cloudflare_access": {
                CONF_ACCESS_CLIENT_ID: " id.access ",
                CONF_ACCESS_CLIENT_SECRET: "secret ",
            },
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_PUSH_URL: PUSH_URL, **ACCESS}
    assert mock_kuma_ok.mock_calls[0][3] == ACCESS_HEADERS


async def test_user_flow_access_incomplete(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A client ID without a secret is rejected without a request."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PUSH_URL: PUSH_URL,
            CONF_INTERVAL: 60,
            "cloudflare_access": {CONF_ACCESS_CLIENT_ID: "id.access"},
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "incomplete_access"}
    assert aioclient_mock.call_count == 0


async def test_reauth_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A denied push starts reauth, which stores working credentials."""
    aioclient_mock.get(PUSH_URL, status=403)
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR

    [flow] = hass.config_entries.flow.async_progress()
    assert flow["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_ACCESS_CLIENT_ID: "id.access"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "incomplete_access"}

    result = await hass.config_entries.flow.async_configure(flow["flow_id"], ACCESS)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], ACCESS)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data == {CONF_PUSH_URL: PUSH_URL, **ACCESS}
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert all(call[3] == ACCESS_HEADERS for call in aioclient_mock.mock_calls)


@pytest.mark.usefixtures("mock_kuma_ok")
async def test_reconfigure_flow(hass: HomeAssistant) -> None:
    """Reconfigure prefills the client ID and can remove the credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="kuma.example.com",
        unique_id=PUSH_URL,
        data={CONF_PUSH_URL: PUSH_URL, **ACCESS},
        options={CONF_INTERVAL: 60},
    )
    await setup_integration(hass, entry)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }
    assert suggested == {CONF_ACCESS_CLIENT_ID: "id.access"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_PUSH_URL: PUSH_URL}
