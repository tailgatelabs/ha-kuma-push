"""Tests for the push client."""

from __future__ import annotations

from unittest.mock import patch

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.kuma_push.api import (
    KumaPushAuthError,
    KumaPushConnectionError,
    KumaPushRejectedError,
    access_headers,
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
    ("client_id", "client_secret"),
    [(None, None), ("id.access", None), (None, "secret"), ("", "secret")],
)
def test_access_headers_incomplete(
    client_id: str | None, client_secret: str | None
) -> None:
    """No headers are built without both halves of the token."""
    assert access_headers(client_id, client_secret) is None


async def test_push_access_headers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Access service token headers are sent with the push."""
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    headers = access_headers("id.access", "secret")
    await async_push(async_get_clientsession(hass), PUSH_URL, headers=headers)

    assert aioclient_mock.mock_calls[0][3] == {
        "CF-Access-Client-Id": "id.access",
        "CF-Access-Client-Secret": "secret",
    }


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
        ({"status": 401}, KumaPushAuthError, "HTTP 401"),
        ({"status": 403, "text": "Forbidden"}, KumaPushAuthError, "HTTP 403"),
        (
            {
                "status": 302,
                "headers": {
                    "Location": "https://team.cloudflareaccess.com/cdn-cgi/access/login/kuma.example.com"
                },
            },
            KumaPushAuthError,
            "HTTP 302",
        ),
        (
            {"status": 302, "headers": {"Location": "/cdn-cgi/access/login"}},
            KumaPushAuthError,
            "HTTP 302",
        ),
        (
            {"status": 301, "headers": {"Location": "https://kuma.example.net/"}},
            KumaPushRejectedError,
            "to https://kuma.example.net/",
        ),
        (
            {"status": 302, "headers": {"Location": "http://[::1"}},
            KumaPushRejectedError,
            "Redirected",
        ),
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
        await async_push(
            async_get_clientsession(hass),
            PUSH_URL,
            headers=access_headers("id.access", "secret"),
        )


@pytest.mark.parametrize(
    ("headers", "follows"),
    [(None, True), ({"CF-Access-Client-Id": "id.access"}, False)],
)
async def test_push_follows_redirects_without_headers(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    headers: dict[str, str] | None,
    follows: bool,
) -> None:
    """Redirects are followed unless Access headers could leak to another host."""
    aioclient_mock.get(PUSH_URL, json={"ok": True})
    session = async_get_clientsession(hass)
    with patch.object(session, "get", wraps=session.get) as mock_get:
        await async_push(session, PUSH_URL, headers=headers)

    assert mock_get.call_args.kwargs["allow_redirects"] is follows


async def test_push_followed_redirect_to_access_login(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Landing on the Access login page after a redirect is an auth failure."""

    async def login_page(
        method: str, url: URL, data: None
    ) -> AiohttpClientMockResponse:
        return AiohttpClientMockResponse(
            method,
            URL("https://team.cloudflareaccess.com/cdn-cgi/access/login/kuma"),
            text="<html>",
        )

    aioclient_mock.get(PUSH_URL, side_effect=login_page)
    with pytest.raises(KumaPushAuthError):
        await async_push(async_get_clientsession(hass), PUSH_URL)
