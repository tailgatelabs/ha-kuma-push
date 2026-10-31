"""Tests for setup, scheduling and entity state."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import PUSH_URL, setup_integration

STATUS = "binary_sensor.kuma_example_com_push_status"
NEXT_PUSH = "sensor.kuma_example_com_next_push"
LAST_SUCCESS = "sensor.kuma_example_com_last_successful_push"


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_kuma_ok: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Setup pushes immediately and exposes the entities."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_kuma_ok.call_count == 1

    now = dt_util.utcnow().replace(microsecond=0)
    assert hass.states.get(STATUS).state == STATE_OFF
    assert hass.states.get(STATUS).attributes["last_error"] is None
    next_push = dt_util.parse_datetime(hass.states.get(NEXT_PUSH).state)
    assert next_push == now + timedelta(seconds=60)
    assert dt_util.parse_datetime(hass.states.get(LAST_SUCCESS).state) == now

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED

    await _tick(hass, freezer)
    assert mock_kuma_ok.call_count == 1


async def test_pushes_on_interval(
    hass: HomeAssistant,
    mock_kuma_ok: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Pushes repeat on the interval and include the previous latency."""
    await setup_integration(hass, mock_config_entry)
    first_next = hass.states.get(NEXT_PUSH).state

    await _tick(hass, freezer)
    assert mock_kuma_ok.call_count == 2
    assert "ping" in mock_kuma_ok.mock_calls[1][1].query
    assert hass.states.get(NEXT_PUSH).state != first_next


async def test_setup_while_failing(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An unreachable server at startup still loads and reports the problem."""
    aioclient_mock.get(PUSH_URL, exc=TimeoutError())
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    status = hass.states.get(STATUS)
    assert status.state == STATE_ON
    assert "Timed out" in status.attributes["last_error"]
    assert hass.states.get(LAST_SUCCESS).state == STATE_UNKNOWN
    assert hass.states.get(NEXT_PUSH).state != STATE_UNKNOWN


async def test_failure_and_recovery(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failures flip the status, keep last success, and log once."""
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    await setup_integration(hass, mock_config_entry)
    last_success = hass.states.get(LAST_SUCCESS).state

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        PUSH_URL, status=404, json={"ok": False, "msg": "Monitor not found"}
    )
    await _tick(hass, freezer)
    await _tick(hass, freezer)

    status = hass.states.get(STATUS)
    assert status.state == STATE_ON
    assert status.attributes["last_error"] == "Monitor not found"
    assert hass.states.get(LAST_SUCCESS).state == last_success
    assert caplog.text.count("Push to Uptime Kuma failed") == 1
    # Latency of a failed push is not reported.
    assert "ping" not in aioclient_mock.mock_calls[-1][1].query

    aioclient_mock.clear_requests()
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    await _tick(hass, freezer)

    assert hass.states.get(STATUS).state == STATE_OFF
    assert hass.states.get(LAST_SUCCESS).state != last_success
    assert "Push to Uptime Kuma recovered" in caplog.text


async def test_pushes_with_entities_disabled(
    hass: HomeAssistant,
    mock_kuma_ok: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Pushing continues without any enabled entity."""
    await setup_integration(hass, mock_config_entry)
    for entity in er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    ):
        entity_registry.async_update_entity(
            entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER
        )
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    calls = mock_kuma_ok.call_count

    await _tick(hass, freezer)
    assert mock_kuma_ok.call_count == calls + 1


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A denied push after setup makes entities unavailable and starts reauth."""
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    await setup_integration(hass, mock_config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(PUSH_URL, status=403)
    await _tick(hass, freezer)

    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    [flow] = hass.config_entries.flow.async_progress()
    assert flow["context"]["source"] == SOURCE_REAUTH
