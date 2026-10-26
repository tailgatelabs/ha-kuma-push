"""Minimal client for Uptime Kuma push monitors."""

from __future__ import annotations

from time import monotonic

import aiohttp
from yarl import URL

from .const import PUSH_PATH, REQUEST_TIMEOUT

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)


class KumaPushError(Exception):
    """Base error for a failed push."""


class KumaPushConnectionError(KumaPushError):
    """Uptime Kuma could not be reached."""


class KumaPushRejectedError(KumaPushError):
    """Uptime Kuma answered but did not accept the push."""


def normalize_push_url(raw: str) -> str:
    """Validate a push URL and strip its query string and fragment.

    Uptime Kuma shows the push URL with ``?status=up&msg=OK&ping=`` appended;
    those parameters are supplied on every push instead.
    """
    try:
        url = URL(raw.strip())
    except ValueError as err:
        raise ValueError("Invalid URL") from err
    if url.scheme not in ("http", "https") or not url.host:
        raise ValueError("URL must be http(s) with a host")
    _, sep, token = url.path.rpartition(PUSH_PATH)
    if not sep or not token.strip("/"):
        raise ValueError(f"URL path must contain {PUSH_PATH}<token>")
    return str(url.with_query(None).with_fragment(None))


async def async_push(
    session: aiohttp.ClientSession, url: str, ping_ms: int | None = None
) -> int:
    """Send an ``up`` heartbeat and return the round-trip time in milliseconds."""
    params = {"status": "up", "msg": "OK"}
    if ping_ms is not None:
        params["ping"] = str(ping_ms)

    start = monotonic()
    try:
        async with session.get(url, params=params, timeout=_TIMEOUT) as resp:
            status = resp.status
            try:
                payload = await resp.json(content_type=None)
            except ValueError:
                payload = None
    except TimeoutError as err:
        raise KumaPushConnectionError("Timed out connecting to Uptime Kuma") from err
    except aiohttp.ClientError as err:
        raise KumaPushConnectionError(
            f"Error connecting to Uptime Kuma: {err or type(err).__name__}"
        ) from err
    latency = round((monotonic() - start) * 1000)

    if not isinstance(payload, dict):
        raise KumaPushRejectedError(f"Unexpected response (HTTP {status})")
    if not payload.get("ok"):
        raise KumaPushRejectedError(payload.get("msg") or f"Rejected (HTTP {status})")
    return latency
