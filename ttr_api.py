"""Async client for the Toontown Rewritten public APIs.

Docs: https://github.com/toontown-rewritten/api-doc
Only uses the *public* endpoints (no auth). The Local/Companion-app API
and Login API are intentionally out of scope for a server-wide bot.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

BASE = "https://www.toontownrewritten.com/api"

ENDPOINTS = {
    "invasions": f"{BASE}/invasions",
    "population": f"{BASE}/population",
    "fieldoffices": f"{BASE}/fieldoffices",
    "doodles": f"{BASE}/doodles",
    "sillymeter": f"{BASE}/sillymeter",
}


class TTRApiClient:
    def __init__(self, user_agent: str, timeout: float = 15.0) -> None:
        self._user_agent = user_agent
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "TTRApiClient":
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": self._user_agent},
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _get(self, url: str) -> dict[str, Any] | None:
        assert self._session is not None, "Use `async with TTRApiClient(...)`"
        try:
            async with self._session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("TTR API request failed for %s: %s", url, e)
            return None

    async def invasions(self) -> dict[str, Any] | None:
        return await self._get(ENDPOINTS["invasions"])

    async def population(self) -> dict[str, Any] | None:
        return await self._get(ENDPOINTS["population"])

    async def field_offices(self) -> dict[str, Any] | None:
        return await self._get(ENDPOINTS["fieldoffices"])

    async def doodles(self) -> dict[str, Any] | None:
        return await self._get(ENDPOINTS["doodles"])

    async def silly_meter(self) -> dict[str, Any] | None:
        return await self._get(ENDPOINTS["sillymeter"])

    async def fetch(self, key: str) -> dict[str, Any] | None:
        """Fetch by feed key (used by the bot's polling loop)."""
        method = {
            "invasions": self.invasions,
            "population": self.population,
            "fieldoffices": self.field_offices,
            "doodles": self.doodles,
            "sillymeter": self.silly_meter,
        }.get(key)
        if method is None:
            raise KeyError(f"Unknown feed key: {key}")
        return await method()
