"""Load complete liked-song metadata without hiding partial upstream failures."""
import asyncio
from typing import Awaitable, Protocol

import httpx
from fastapi import HTTPException


DETAIL_BATCH_SIZE = 200
LIKED_PLAYLIST_TYPE = 5


class LikesClient(Protocol):
    async def user_account(self, *, cookie: str) -> dict: ...
    async def likelist(self, *, uid: str, cookie: str) -> dict: ...
    async def song_detail(self, *, song_id: str, cookie: str) -> dict: ...
    async def user_playlist(self, *, uid: str, cookie: str) -> dict: ...
    async def playlist_detail(self, playlist_id: str, *, cookie: str) -> dict: ...


def invalid_response(label: str) -> HTTPException:
    return HTTPException(status_code=502, detail=f"网易云{label}返回无效数据")


async def request_data(request: Awaitable[dict], label: str) -> dict:
    try:
        data = await request
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=502, detail=f"网易云{label}请求失败（HTTP {error.response.status_code}）",
        ) from None
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"网易云{label}请求超时") from None
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail=f"网易云{label}网络请求失败") from None
    except ValueError:
        raise invalid_response(label) from None
    if not isinstance(data, dict) or data.get("code") not in (None, 200):
        raise invalid_response(label)
    return data


def require_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise invalid_response(label)
    return value


def require_id(value: object, label: str) -> str:
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise invalid_response(label)
    return str(value)


async def fetch_song_batch(client: LikesClient, *, ids: list[str], cookie: str) -> list[dict]:
    data = await request_data(client.song_detail(song_id=",".join(ids), cookie=cookie), "歌曲详情")
    songs = require_list(data.get("songs"), "歌曲详情")
    if any(not isinstance(song, dict) or "id" not in song for song in songs):
        raise invalid_response("歌曲详情")
    return songs


def find_liked_playlist(playlists: list, uid: str) -> str:
    for playlist in playlists:
        if not isinstance(playlist, dict):
            raise invalid_response("用户歌单")
        creator = playlist.get("creator") or {}
        if not isinstance(creator, dict):
            raise invalid_response("用户歌单")
        owner = creator.get("userId")
        if str(playlist.get("specialType")) != str(LIKED_PLAYLIST_TYPE):
            continue
        if owner is not None and str(owner) != uid:
            continue
        return require_id(playlist.get("id"), "用户歌单")
    raise HTTPException(status_code=502, detail="网易云未返回当前账号的喜欢歌单，无法读取收藏时间")


def timestamp_map(entries: list) -> dict[str, int]:
    result = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise invalid_response("收藏时间")
        identifier = require_id(entry.get("id"), "收藏时间")
        added_at = entry.get("at")
        if added_at is None:
            continue
        value = require_id(added_at, "收藏时间")
        result[identifier] = int(value)
    return result


async def fetch_added_times(client: LikesClient, *, uid: str, cookie: str) -> dict[str, int]:
    data = await request_data(client.user_playlist(uid=uid, cookie=cookie), "用户歌单")
    playlist_id = find_liked_playlist(require_list(data.get("playlist"), "用户歌单"), uid)
    detail = await request_data(client.playlist_detail(playlist_id, cookie=cookie), "收藏时间")
    playlist = detail.get("playlist")
    if not isinstance(playlist, dict):
        raise invalid_response("收藏时间")
    return timestamp_map(require_list(playlist.get("trackIds"), "收藏时间"))


async def fetch_likes(client: LikesClient, *, cookie: str, offset: int = 0, limit: int = 0) -> dict:
    account = await request_data(client.user_account(cookie=cookie), "账号信息")
    profile = account.get("profile")
    if not isinstance(profile, dict) or not profile.get("userId"):
        raise HTTPException(status_code=400, detail="无法通过 Cookie 确认网易云账号，请重新登录")
    uid = require_id(profile["userId"], "账号信息")
    data = await request_data(client.likelist(uid=uid, cookie=cookie), "喜欢列表")
    ids = [require_id(value, "喜欢列表") for value in require_list(data.get("ids"), "喜欢列表")]
    page_offset = max(0, offset) if limit > 0 else 0
    page_ids = ids[page_offset:page_offset + limit] if limit > 0 else ids
    chunks = [page_ids[start:start + DETAIL_BATCH_SIZE] for start in range(0, len(page_ids), DETAIL_BATCH_SIZE)]
    batches = await asyncio.gather(*(fetch_song_batch(client, ids=chunk, cookie=cookie) for chunk in chunks))
    added_times = await fetch_added_times(client, uid=uid, cookie=cookie) if page_ids else {}
    by_id = {str(song["id"]): song for batch in batches for song in batch}
    songs = [
        {**by_id[identifier], **({"added_at": added_times[identifier]} if identifier in added_times else {})}
        for identifier in page_ids if identifier in by_id
    ]
    return {
        **data, "songs": songs, "total": len(ids), "offset": page_offset, "limit": max(0, limit),
        "has_more": limit > 0 and page_offset + limit < len(ids),
    }
