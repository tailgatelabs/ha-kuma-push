"""Tests for the push client."""

from __future__ import annotations

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.kuma_push.api import (
    KumaPushConnectionError,
    KumaPushRejectedError,
    async_push,
    normalize_push_url,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import PUSH_URL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (PUSH_URL, PUSH_URL),
        (f"  {PUSH_URL}?status=up&msg=OK&ping=  ", PUSH_URL),
        (f"{PUSH_URL}#frag", PUSH_URL),
        (
            "http://10.0.0.2:3001/kuma/api/push/tok",
            "http://10.0.0.2:3001/kuma/api/push/tok",
        ),
    ],
)
def test_normalize_push_url(raw: str, expected: str) -> None:
    """Valid URLs are normalized."""
    assert normalize_push_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "kuma.example.com/api/push/abc",
        "ftp://kuma.example.com/api/push/abc",
        "https://kuma.example.com/api/push/",
        "https://kuma.example.com/api/status/abc",
        "https:///api/push/abc",
        "http://[::1/api/push/abc",
    ],
)
def test_normalize_push_url_invalid(raw: str) -> None:
    """Invalid URLs raise ValueError."""
    with pytest.raises(ValueError, match=r"."):
        normalize_push_url(raw)


async def test_push_params(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Pushes send status, msg and the previous round-trip as ping."""
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    session = async_get_clientsession(hass)

    assert isinstance(await async_push(session, PUSH_URL), int)
    assert await async_push(session, PUSH_URL, 42) >= 0

    first, second = (call[1] for call in aioclient_mock.mock_calls)
    assert dict(first.query) == {"status": "up", "msg": "OK"}
    assert dict(second.query) == {"status": "up", "msg": "OK", "ping": "42"}


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"exc": TimeoutError()}, KumaPushConnectionError, "Timed out"),
        (
            {"exc": aiohttp.ClientConnectionError("refused")},
            KumaPushConnectionError,
            "refused",
        ),
        (
            {"status": 404, "json": {"ok": False, "msg": "Monitor not found"}},
            KumaPushRejectedError,
            "Monitor not found",
        ),
        ({"json": {"ok": False}}, KumaPushRejectedError, "HTTP 200"),
        ({"status": 502, "text": "<html>"}, KumaPushRejectedError, "HTTP 502"),
        ({"json": ["ok"]}, KumaPushRejectedError, "Unexpected response"),
    ],
)
async def test_push_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict,
    error: type[Exception],
    message: str,
) -> None:
    """Failures map to typed errors with readable messages."""
    aioclient_mock.get(PUSH_URL, **kwargs)
    with pytest.raises(error, match=message):
        await async_push(async_get_clientsession(hass), PUSH_URL)
