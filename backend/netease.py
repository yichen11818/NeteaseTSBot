from __future__ import annotations

from typing import Any

import httpx

from .config import settings


class NeteaseClient:
    def __init__(self) -> None:
        self._base = settings.netease_api_base.rstrip("/")

    async def _get(self, path: str, *, params: dict[str, Any] | None = None, cookie: str | None = None) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if cookie:
            headers["Cookie"] = cookie
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            r = await client.get(f"{self._base}{path}", params=params)
            r.raise_for_status()
            return r.json()

    async def search(self, keywords: str, limit: int = 20, type_: int = 1) -> dict[str, Any]:
        return await self._get(
            "/search",
            params={"keywords": keywords, "limit": limit, "type": type_},
        )

    async def song_url(self, song_id: str, cookie: str | None = None) -> dict[str, Any]:
        return await self._get("/song/url", params={"id": song_id}, cookie=cookie)

    async def playlist_detail(self, playlist_id: str) -> dict[str, Any]:
        return await self._get("/playlist/detail", params={"id": playlist_id})

    async def user_account(self, cookie: str) -> dict[str, Any]:
        return await self._get("/user/account", cookie=cookie)

    async def user_playlist(self, uid: str, cookie: str) -> dict[str, Any]:
        return await self._get("/user/playlist", params={"uid": uid}, cookie=cookie)

    async def likelist(self, uid: str, cookie: str) -> dict[str, Any]:
        return await self._get("/likelist", params={"uid": uid}, cookie=cookie)
