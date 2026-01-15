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

    # 搜索相关功能
    async def search_suggest(self, keywords: str) -> dict[str, Any]:
        """搜索建议"""
        return await self._get("/search/suggest", params={"keywords": keywords})

    async def search_hot(self) -> dict[str, Any]:
        """热搜列表"""
        return await self._get("/search/hot")

    async def search_hot_detail(self) -> dict[str, Any]:
        """热搜列表详细"""
        return await self._get("/search/hot/detail")

    async def search_default(self) -> dict[str, Any]:
        """默认搜索关键词"""
        return await self._get("/search/default")

    # 歌单相关功能
    async def playlist_catlist(self) -> dict[str, Any]:
        """歌单分类"""
        return await self._get("/playlist/catlist")

    async def playlist_hot(self) -> dict[str, Any]:
        """热门歌单分类"""
        return await self._get("/playlist/hot")

    async def top_playlist(self, cat: str = "全部", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """歌单 (网友精选碟)"""
        return await self._get("/top/playlist", params={"cat": cat, "limit": limit, "offset": offset})

    async def top_playlist_highquality(self, cat: str = "全部", limit: int = 20) -> dict[str, Any]:
        """获取精品歌单"""
        return await self._get("/top/playlist/highquality", params={"cat": cat, "limit": limit})

    async def related_playlist(self, playlist_id: str, cookie: str | None = None) -> dict[str, Any]:
        """相关歌单推荐"""
        return await self._get("/related/playlist", params={"id": playlist_id}, cookie=cookie)

    # 评论相关功能
    async def comment_music(self, song_id: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        """歌曲评论"""
        return await self._get("/comment/music", params={"id": song_id, "limit": limit, "offset": offset})

    async def comment_hot(self, song_id: str, type_: int = 0, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        """热门评论"""
        return await self._get("/comment/hot", params={"id": song_id, "type": type_, "limit": limit, "offset": offset})

    # 用户相关功能
    async def user_detail(self, uid: str, cookie: str | None = None) -> dict[str, Any]:
        """获取用户详情"""
        return await self._get("/user/detail", params={"uid": uid}, cookie=cookie)

    async def user_record(self, uid: str, type_: int = 1, cookie: str | None = None) -> dict[str, Any]:
        """获取用户播放记录 type: 1=最近一周, 0=所有时间"""
        return await self._get("/user/record", params={"uid": uid, "type": type_}, cookie=cookie)

    async def user_subcount(self, cookie: str) -> dict[str, Any]:
        """获取用户信息 , 歌单，收藏，mv, dj 数量"""
        return await self._get("/user/subcount", cookie=cookie)

    # 推荐相关功能
    async def personalized(self, limit: int = 30, cookie: str | None = None) -> dict[str, Any]:
        """推荐歌单"""
        return await self._get("/personalized", params={"limit": limit}, cookie=cookie)

    async def personalized_newsong(self, cookie: str | None = None) -> dict[str, Any]:
        """推荐新音乐"""
        return await self._get("/personalized/newsong", cookie=cookie)

    async def recommend_songs(self, cookie: str) -> dict[str, Any]:
        """每日推荐歌曲"""
        return await self._get("/recommend/songs", cookie=cookie)

    async def recommend_resource(self, cookie: str) -> dict[str, Any]:
        """每日推荐歌单"""
        return await self._get("/recommend/resource", cookie=cookie)

    # 歌手相关功能
    async def artist_top_song(self, artist_id: str) -> dict[str, Any]:
        """歌手热门50首歌曲"""
        return await self._get("/artist/top/song", params={"id": artist_id})

    async def artists(self, artist_id: str) -> dict[str, Any]:
        """获取歌手单曲"""
        return await self._get("/artists", params={"id": artist_id})

    # 收藏相关功能
    async def like(self, song_id: str, like: bool, cookie: str) -> dict[str, Any]:
        """喜欢音乐"""
        return await self._get("/like", params={"id": song_id, "like": "true" if like else "false"}, cookie=cookie)

    async def playlist_subscribe(self, playlist_id: str, subscribe: bool, cookie: str) -> dict[str, Any]:
        """收藏/取消收藏歌单"""
        t = 1 if subscribe else 2
        return await self._get("/playlist/subscribe", params={"t": t, "id": playlist_id}, cookie=cookie)

    # 歌单管理功能
    async def playlist_create(self, name: str, privacy: bool = False, cookie: str | None = None) -> dict[str, Any]:
        """新建歌单"""
        return await self._get("/playlist/create", params={"name": name, "privacy": 10 if privacy else 0}, cookie=cookie)

    async def playlist_tracks(self, op: str, pid: str, tracks: str, cookie: str) -> dict[str, Any]:
        """对歌单添加或删除歌曲 op: add/del"""
        return await self._get("/playlist/tracks", params={"op": op, "pid": pid, "tracks": tracks}, cookie=cookie)

    # 登录相关功能
    async def login_cellphone(self, phone: str, password: str) -> dict[str, Any]:
        """手机登录"""
        return await self._get("/login/cellphone", params={"phone": phone, "password": password})

    async def login_email(self, email: str, password: str) -> dict[str, Any]:
        """邮箱登录"""
        return await self._get("/login", params={"email": email, "password": password})

    async def login_status(self, cookie: str) -> dict[str, Any]:
        """登录状态"""
        return await self._get("/login/status", cookie=cookie)

    async def logout(self, cookie: str) -> dict[str, Any]:
        """退出登录"""
        return await self._get("/logout", cookie=cookie)
