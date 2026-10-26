"""Fixtures for Uptime Kuma Push tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.kuma_push.const import CONF_INTERVAL, CONF_PUSH_URL, DOMAIN
from homeassistant.core import HomeAssistant

PUSH_URL = "https://kuma.example.com/api/push/abc123"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="kuma.example.com",
        unique_id=PUSH_URL,
        data={CONF_PUSH_URL: PUSH_URL},
        options={CONF_INTERVAL: 60},
    )


@pytest.fixture
def mock_kuma_ok(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Uptime Kuma accepting pushes."""
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    return aioclient_mock


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip entry setup in config flow tests."""
    with patch(
        "custom_components.kuma_push.async_setup_entry", return_value=True
    ) as mock:
        yield mock


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
