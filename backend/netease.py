from __future__ import annotations

from typing import Any
import time

import httpx

from .config import settings


class NeteaseClient:
    def __init__(self) -> None:
        self._base = settings.netease_api_base.rstrip("/")

    async def _get(self, path: str, *, params: dict[str, Any] | None = None, cookie: str | None = None) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if cookie:
            # httpx will reject header values containing newlines/control chars.
            c = cookie.strip()
            if c.lower().startswith("cookie:"):
                c = c.split(":", 1)[1].strip()
            c = c.replace("\r", "").replace("\n", "")
            headers["Cookie"] = c
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            r = await client.get(f"{self._base}{path}", params=params)
            r.raise_for_status()
            return r.json()

    async def search(self, keywords: str, limit: int = 20, type_: int = 1) -> dict[str, Any]:
        return await self._get(
            "/search",
            params={"keywords": keywords, "limit": limit, "type": type_},
        )

    async def song_url(self, song_id: str, cookie: str | None = None, br: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"id": song_id, "timestamp": int(time.time() * 1000)}
        if br is not None:
            params["br"] = int(br)
        return await self._get("/song/url", params=params, cookie=cookie)

    async def song_detail(self, song_id: str, cookie: str | None = None) -> dict[str, Any]:
        return await self._get("/song/detail", params={"ids": song_id}, cookie=cookie)

    async def lyric(self, song_id: str, cookie: str | None = None) -> dict[str, Any]:
        return await self._get("/lyric", params={"id": song_id}, cookie=cookie)

    async def playlist_detail(self, playlist_id: str, cookie: str | None = None) -> dict[str, Any]:
        return await self._get("/playlist/detail", params={"id": playlist_id}, cookie=cookie)

    async def qr_key(self) -> dict[str, Any]:
        return await self._get("/login/qr/key", params={"timestamp": int(time.time() * 1000)})

    async def qr_create(self, key: str, *, qrimg: int = 1) -> dict[str, Any]:
        return await self._get(
            "/login/qr/create",
            params={"key": key, "qrimg": int(qrimg), "timestamp": int(time.time() * 1000)},
        )

    async def qr_check(self, key: str) -> dict[str, Any]:
        return await self._get("/login/qr/check", params={"key": key, "timestamp": int(time.time() * 1000)})

    async def user_account(self, cookie: str) -> dict[str, Any]:
        return await self._get("/user/account", cookie=cookie)

    async def user_playlist(self, uid: str, cookie: str) -> dict[str, Any]:
        return await self._get("/user/playlist", params={"uid": uid}, cookie=cookie)

    async def likelist(self, uid: str, cookie: str) -> dict[str, Any]:
        return await self._get("/likelist", params={"uid": uid}, cookie=cookie)
