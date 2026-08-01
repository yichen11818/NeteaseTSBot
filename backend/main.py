from __future__ import annotations

import asyncio
from collections import deque
import hashlib
from html import unescape
import hmac
import math
import os
import re
import time
import uuid
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .bilibili_cache import prune_audio_cache
from .bilibili_auth import (
    close_all_bilibili_qr_sessions,
    cookie_string_to_dict,
    fetch_bilibili_subtitle_candidates_via_playwright,
    is_playwright_available,
    is_playwright_runtime_available,
    poll_bilibili_qr_login_session,
    start_bilibili_qr_login_session,
)
from .crypto import decrypt_text, encrypt_text
from .db import create_db_and_tables, get_database_url, get_session, get_sqlite_db_path, new_session
from .models import HistoryItem, QueueItem, Secret
from .netease import NeteaseClient
from .netease_cookie import extract_netease_auth_cookie, has_netease_auth_cookie
from .qqmusic import QQMusicClient
from .voice_client import VoiceClient
from .config import settings
from .logger import logger

app = FastAPI(title="tsbot-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

netease = NeteaseClient()
qqmusic = QQMusicClient()
voice = VoiceClient()

REPO_ROOT = Path(__file__).resolve().parent.parent
BILIBILI_AUDIO_DIR = REPO_ROOT / "tmp" / "bilibili_audio"
BILIBILI_AUDIO_CACHE_TTL_SECONDS = max(0, settings.bilibili_audio_cache_ttl_hours) * 3600
BILIBILI_AUDIO_CACHE_MAX_BYTES = max(0, settings.bilibili_audio_cache_max_mb) * 1024 * 1024
BILIBILI_AUDIO_PARTIAL_TTL_SECONDS = max(0, settings.bilibili_audio_partial_ttl_minutes) * 60
_BILIBILI_VIDEO_ID_RE = re.compile(r"(BV[0-9A-Za-z]+|av\d+)", re.IGNORECASE)
_BILIBILI_TAG_RE = re.compile(r"<[^>]+>")
_BILIBILI_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_BILIBILI_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
_BILIBILI_DEFAULT_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "referer": "https://www.bilibili.com/",
    "accept": "application/json, text/plain, */*",
}
_bilibili_download_locks: dict[str, asyncio.Lock] = {}
_BILIBILI_VIEW_SUMMARY_CACHE_TTL_S = 600.0
_BILIBILI_VIEW_SUMMARY_CONCURRENCY = 6
_bilibili_view_summary_cache: dict[str, tuple[float, dict[str, object]]] = {}
_bilibili_view_summary_semaphore = asyncio.Semaphore(_BILIBILI_VIEW_SUMMARY_CONCURRENCY)
_BILIBILI_SUBTITLE_CACHE_TTL_S = 1800.0
_bilibili_subtitle_cache: dict[str, tuple[float, list[LyricLine]]] = {}
_NETEASE_QUALITY_LEVELS = (
    "standard",
    "higher",
    "exhigh",
    "lossless",
    "hires",
    "jyeffect",
    "sky",
    "dolby",
    "jymaster",
)
_NETEASE_QUEUE_META_PREFIX = "__netease_level__:"

# Add OPTIONS handler for CORS preflight requests
@app.options("/{full_path:path}")
async def options_handler():
    return {"message": "OK"}


def _normalize_request_path(path: str) -> str:
    normalized = (path or "/").rstrip("/")
    return normalized or "/"


def _split_env_multiline(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    return [line.strip() for line in raw.replace("\\n", "\n").splitlines() if line.strip()]


def _get_request_api_token(request: Request) -> str:
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-api-token") or "").strip()


def _path_requires_api_token(path: str) -> bool:
    if not settings.get_api_tokens():
        return False

    normalized = _normalize_request_path(path)
    if normalized in {"/", "/docs", "/redoc", "/openapi.json"}:
        return False
    if normalized.startswith("/docs/") or normalized.startswith("/redoc/"):
        return False
    if normalized == "/admin" or normalized.startswith("/admin/"):
        return False
    return True


def _check_api_token(request: Request) -> str | None:
    tokens = settings.get_api_tokens()
    if not tokens:
        return None

    provided = _get_request_api_token(request)
    if not provided:
        return "missing api token"
    if any(hmac.compare_digest(provided, token) for token in tokens):
        return None
    return "invalid api token"


@app.middleware("http")
async def api_token_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or not _path_requires_api_token(request.url.path):
        return await call_next(request)

    error = _check_api_token(request)
    if error is not None:
        return JSONResponse(
            status_code=401,
            content={"detail": error},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)

_chat_task: asyncio.Task[None] | None = None
_current_queue_item_id: int | None = None
_pending_queue_item_id: int | None = None
_current_source_url: str = ""
_playback_lock = asyncio.Lock()
_play_request_generation: int = 0
_play_started_at: float | None = None
_paused_at: float | None = None
_paused_total_s: float = 0.0
_current_duration_ms: int = 0
_current_artist: str | None = None
_current_album: str | None = None
_current_artwork_url: str | None = None

_shuffle_enabled: bool = False
_repeat_mode: str = "none"  # "none", "all", "one"
_shuffle_queue: list[int] = []
_current_shuffle_index: int = -1

_recent_ts_chats: deque[dict] = deque(maxlen=100)

_pending_playlist_select: list[dict] | None = None
_pending_playlist_keywords: str = ""

_main_loop: asyncio.AbstractEventLoop | None = None
_ts_desc_task: asyncio.Task[None] | None = None
_ts_desc_requested: bool = False
_ts_desc_last_sent_at: float = 0.0


class SearchResponse(BaseModel):
    raw: dict


class AddQueueRequest(BaseModel):
    track_id: str
    title: str
    artist: str = ""
    source_url: str


class AddNeteaseQueueRequest(BaseModel):
    song_id: str
    title: str
    artist: str = ""
    album: str = ""
    duration_ms: int | None = None
    cover_url: str = ""
    level: str = "auto"
    play_now: bool = False


class AddQQMusicQueueRequest(BaseModel):
    song_mid: str
    title: str
    artist: str = ""
    play_now: bool = False
    quality: str = "320"
    album_mid: str = ""
    duration_ms: int | None = None


class AddBilibiliQueueRequest(BaseModel):
    video_id: str
    title: str
    artist: str = ""
    album: str = ""
    duration_ms: int | None = None
    cover_url: str = ""
    play_now: bool = False


class VolumeUpdateRequest(BaseModel):
    volume_percent: int


class AudioFxUpdateRequest(BaseModel):
    pan: float | None = None
    width: float | None = None
    swap_lr: bool | None = None
    bass_db: float | None = None
    reverb_mix: float | None = None


class AdminCookieSetRequest(BaseModel):
    cookie: str


class TSClientDescriptionRequest(BaseModel):
    description: str


class ExternalPlayerActionRequest(BaseModel):
    action: str


class ExternalQueueRequest(BaseModel):
    source: str = "netease"
    keywords: str = ""
    song_id: str = ""
    song_mid: str = ""
    video_id: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    album_mid: str = ""
    duration_ms: int | None = None
    cover_url: str = ""
    level: str = "auto"
    quality: str = "320"
    play_now: bool = False


@app.on_event("startup")
async def _startup() -> None:
    global _chat_task
    global _main_loop
    create_db_and_tables()

    _main_loop = asyncio.get_running_loop()
    session = new_session()
    try:
        row = session.get(Secret, "voice_volume")
        if row and row.value:
            try:
                await voice.set_volume(int(row.value))
            except Exception:
                pass
    finally:
        session.close()

    _schedule_ts_description_update()

    if _chat_task is None or _chat_task.done():
        _chat_task = asyncio.create_task(_chat_command_worker())


@app.on_event("shutdown")
async def _shutdown() -> None:
    global _chat_task
    if _chat_task is not None:
        _chat_task.cancel()
        _chat_task = None
    await close_all_bilibili_qr_sessions()
    await voice.close()


async def _set_now_playing_queue_item(
    item_id: int | None,
    source_url: str = "",
    *,
    duration_ms: int | None = None,
    artist: str = "",
    album: str = "",
    artwork_url: str = "",
) -> None:
    global _current_queue_item_id, _current_source_url, _play_started_at, _paused_at, _paused_total_s, _current_duration_ms
    global _current_artist, _current_album, _current_artwork_url
    async with _playback_lock:
        _current_queue_item_id = item_id
        _current_source_url = (source_url or "").strip()

        if item_id is None:
            _play_started_at = None
            _paused_at = None
            _paused_total_s = 0.0
            _current_duration_ms = 0
            _current_artist = ""
            _current_album = ""
            _current_artwork_url = ""
        else:
            _play_started_at = time.monotonic()
            _paused_at = None
            _paused_total_s = 0.0
            _current_duration_ms = int(duration_ms or 0)
            _current_artist = (artist or "").strip()
            _current_album = (album or "").strip()
            _current_artwork_url = (artwork_url or "").strip()

    _schedule_ts_description_update()


async def _build_ts_description(*, queue_preview: int = 5) -> str:
    # Snapshot playback state under lock
    async with _playback_lock:
        cur_id = _current_queue_item_id
        paused = _play_started_at is not None and _paused_at is not None

    lines: list[str] = []
    title_lines = _split_env_multiline(os.getenv("TSBOT_TS3_CLIENT_DESCRIPTION_TITLE"))
    intro_lines = _split_env_multiline(os.getenv("TSBOT_TS3_CLIENT_DESCRIPTION_INTRO"))
    if title_lines:
        lines.extend(title_lines)
        lines.append("")

    session = new_session()
    try:
        if cur_id:
            cur = session.get(QueueItem, int(cur_id))
            if cur:
                t = (cur.title or "").strip()
                a = (cur.artist or "").strip()
                state = "暂停" if paused else "正在播放"
                if a:
                    lines.append(f"{state}: {t} - {a}")
                else:
                    lines.append(f"{state}: {t}")
            else:
                lines.append("正在播放: (未知)")

            q = (
                select(QueueItem)
                .where(QueueItem.id >= int(cur_id))
                .order_by(QueueItem.id.asc())
                .limit(int(queue_preview))
            )
            rows = session.execute(q).scalars().all()
        else:
            lines.append("状态: 空闲")
            q = select(QueueItem).order_by(QueueItem.id.asc()).limit(int(queue_preview))
            rows = session.execute(q).scalars().all()

        if rows:
            lines.append("队列:")
            for i, r in enumerate(rows, 1):
                t = (r.title or "").strip()
                a = (r.artist or "").strip()
                if a:
                    lines.append(f"{i}. {t} - {a}")
                else:
                    lines.append(f"{i}. {t}")
        else:
            lines.append("队列: 空")
    finally:
        session.close()

    if intro_lines:
        lines.append("")
        lines.extend(intro_lines)

    desc = "\n".join(lines).strip()
    if len(desc) > 700:
        desc = desc[:700]
    return desc


def _schedule_ts_description_update() -> None:
    global _ts_desc_task, _ts_desc_requested

    _ts_desc_requested = True

    def _ensure_task() -> None:
        global _ts_desc_task
        if _ts_desc_task is None or _ts_desc_task.done():
            _ts_desc_task = asyncio.create_task(_ts_desc_worker())

    try:
        asyncio.get_running_loop()
        _ensure_task()
    except RuntimeError:
        # Called from a threadpool (sync FastAPI endpoints).
        if _main_loop is not None:
            _main_loop.call_soon_threadsafe(_ensure_task)


async def _ts_desc_worker() -> None:
    global _ts_desc_requested, _ts_desc_last_sent_at

    # Debounce bursts into one update.
    while _ts_desc_requested:
        _ts_desc_requested = False
        await asyncio.sleep(0.8)
        if _ts_desc_requested:
            continue

        # Rate limit: avoid spamming TS3 with clientupdate.
        now = time.time()
        if now - _ts_desc_last_sent_at < 3.0:
            await asyncio.sleep(3.0 - (now - _ts_desc_last_sent_at))

        try:
            desc = await _build_ts_description(queue_preview=5)
            await voice.set_client_description(desc)
            _ts_desc_last_sent_at = time.time()
        except Exception:
            pass


async def _take_now_playing_if_match(*, source_url: str) -> int | None:
    """If current playing source_url matches, clear it and return queue item id."""
    global _current_queue_item_id, _current_source_url, _play_started_at, _paused_at, _paused_total_s, _current_duration_ms
    global _current_artist, _current_album, _current_artwork_url
    src = (source_url or "").strip()
    async with _playback_lock:
        if not _current_queue_item_id:
            return None
        if not _current_source_url:
            return None
        if src != _current_source_url:
            return None
        item_id = _current_queue_item_id
        _current_queue_item_id = None
        _current_source_url = ""
        _play_started_at = None
        _paused_at = None
        _paused_total_s = 0.0
        _current_duration_ms = 0
        _current_artist = ""
        _current_album = ""
        _current_artwork_url = ""
        return item_id


async def _begin_play_request(item_id: int | None = None) -> int:
    global _play_request_generation, _pending_queue_item_id
    async with _playback_lock:
        _play_request_generation += 1
        _pending_queue_item_id = item_id
        return _play_request_generation


async def _invalidate_play_requests() -> int:
    global _play_request_generation, _pending_queue_item_id
    async with _playback_lock:
        _play_request_generation += 1
        _pending_queue_item_id = None
        return _play_request_generation


async def _is_play_request_current(request_generation: int) -> bool:
    async with _playback_lock:
        return request_generation == _play_request_generation


async def _clear_pending_queue_item_if_match(item_id: int | None) -> bool:
    global _pending_queue_item_id
    if item_id is None:
        return False
    async with _playback_lock:
        if _pending_queue_item_id != item_id:
            return False
        _pending_queue_item_id = None
        return True


def _get_bilibili_duration_limit_ms() -> int | None:
    limit_minutes = int(getattr(settings, "bilibili_max_duration_minutes", 0) or 0)
    if limit_minutes <= 0:
        return None
    return limit_minutes * 60 * 1000


def _ensure_bilibili_duration_allowed(duration_ms: int | None, *, video_id: str, title: str = "") -> None:
    limit_ms = _get_bilibili_duration_limit_ms()
    resolved_duration_ms = _coerce_positive_int(duration_ms)
    if limit_ms is None or resolved_duration_ms is None or resolved_duration_ms <= limit_ms:
        return

    actual_minutes = math.ceil(resolved_duration_ms / 60000)
    limit_minutes = math.ceil(limit_ms / 60000)
    label = (title or video_id).strip() or video_id
    raise HTTPException(
        status_code=400,
        detail=f"B站视频时长过长，已拒绝播放: {label} ({actual_minutes} 分钟，超过 {limit_minutes} 分钟上限)",
    )


async def _mark_playback_paused() -> None:
    global _paused_at
    async with _playback_lock:
        if _play_started_at is None:
            return
        if _paused_at is not None:
            return
        _paused_at = time.monotonic()

    _schedule_ts_description_update()


async def _mark_playback_resumed() -> None:
    global _paused_at, _paused_total_s
    async with _playback_lock:
        if _play_started_at is None:
            return
        if _paused_at is None:
            return
        _paused_total_s += max(0.0, time.monotonic() - _paused_at)
        _paused_at = None

    _schedule_ts_description_update()


async def _mark_playback_seeked(position_s: float) -> None:
    global _play_started_at, _paused_at, _paused_total_s
    target = max(0.0, float(position_s))
    now = time.monotonic()
    async with _playback_lock:
        if _current_queue_item_id is None or not _current_source_url:
            return
        _play_started_at = now - target
        _paused_total_s = 0.0
        if _paused_at is not None:
            _paused_at = now

    _schedule_ts_description_update()


def _resolve_playback_position_s(*, now_s: float, started_at: float, paused_at: float | None, paused_total_s: float) -> float:
    if paused_at is not None:
        pos = paused_at - started_at - paused_total_s
    else:
        pos = now_s - started_at - paused_total_s
    return max(0.0, pos)


async def _hydrate_bilibili_track_metadata(
    *,
    video_id: str,
    title: str,
    artist: str = "",
    album: str = "",
    artwork_url: str = "",
    duration_ms: int | None = None,
) -> tuple[int | None, str, str, str]:
    resolved_duration_ms = _coerce_positive_int(duration_ms)
    resolved_artist = (artist or "").strip()
    resolved_album = (album or "").strip()
    resolved_artwork_url = (artwork_url or "").strip()

    if (
        resolved_duration_ms is None
        or not resolved_artist
        or not resolved_album
        or not resolved_artwork_url
    ):
        metadata = await _extract_bilibili_video_info(video_id)
        if resolved_duration_ms is None:
            resolved_duration_ms = _coerce_positive_int((metadata or {}).get("duration_ms"))
        if not resolved_artist:
            resolved_artist = str((metadata or {}).get("artist") or "").strip()
        if not resolved_album:
            resolved_album = str((metadata or {}).get("album") or "").strip()
        if not resolved_artwork_url:
            resolved_artwork_url = str((metadata or {}).get("artwork_url") or "").strip()

    _ensure_bilibili_duration_allowed(resolved_duration_ms, video_id=video_id, title=title)
    return resolved_duration_ms, resolved_artist, resolved_album, resolved_artwork_url


async def _play_queue_item_internal(item_id: int, *, requested_by: str) -> bool:
    session = new_session()
    play_request_generation: int | None = None
    try:
        item = session.get(QueueItem, item_id)
        if not item:
            return False
        play_request_generation = await _begin_play_request(int(item.id))

        notice = ""
        duration_ms: int | None = item.duration
        artist = str(item.artist or "")
        album = str(item.album or "")
        artwork_url = str(item.cover_url or "")
        source_url = str(item.source_url or "")
        playback_source_url = source_url
        if item.track_id.startswith("netease:"):
            cookie = _get_admin_cookie(session)
            song_id = item.track_id.split(":", 1)[1]
            quality_level = _extract_netease_queue_level(source_url)
            playback_source_url, _trial, notice, duration_ms, artist, album, artwork_url = await _resolve_netease_playback_payload(
                song_id=song_id,
                cookie=cookie,
                artist=artist,
                album=album,
                artwork_url=artwork_url,
                duration_ms=duration_ms,
                quality_level=quality_level,
            )

            if not await _is_play_request_current(play_request_generation):
                return True

            item.source_url = _encode_netease_queue_source(quality_level, playback_source_url)
            item.album = album
            item.duration = duration_ms
            item.cover_url = artwork_url
            if artist:
                item.artist = artist

            session.add(item)
            session.commit()
        elif item.track_id.startswith("bilibili:"):
            video_id = item.track_id.split(":", 1)[1]
            duration_ms, artist, album, artwork_url = await _hydrate_bilibili_track_metadata(
                video_id=video_id,
                title=str(item.title or ""),
                artist=artist,
                album=album,
                artwork_url=artwork_url,
                duration_ms=duration_ms,
            )

            if not await _is_play_request_current(play_request_generation):
                return True

            playback_source_url, duration_ms, artist, album, artwork_url = await _resolve_bilibili_playback_payload(
                video_id=video_id,
                artist=artist,
                album=album,
                artwork_url=artwork_url,
                duration_ms=duration_ms,
            )

            if not await _is_play_request_current(play_request_generation):
                return True

            item.source_url = playback_source_url
            item.album = album
            item.duration = duration_ms
            item.cover_url = artwork_url
            if artist:
                item.artist = artist

            session.add(item)
            session.commit()
        else:
            item.source_url = playback_source_url

        if not await _is_play_request_current(play_request_generation):
            return True

        await _set_now_playing_queue_item(
            int(item.id),
            playback_source_url,
            duration_ms=duration_ms,
            artist=artist,
            album=album,
            artwork_url=artwork_url,
        )

        if not await _is_play_request_current(play_request_generation):
            await _take_now_playing_if_match(source_url=playback_source_url)
            return True

        await voice.play(source_url=playback_source_url, title=item.title, requested_by=requested_by, notice=notice)

        if not await _is_play_request_current(play_request_generation):
            return True

        hist = HistoryItem(
            track_id=item.track_id,
            title=item.title,
            artist=item.artist,
            album=item.album,
            duration=item.duration,
            cover_url=item.cover_url,
            source_url=playback_source_url,
            requested_by=requested_by,
        )
        session.add(hist)
        session.commit()
        return True
    finally:
        if play_request_generation is not None:
            await _clear_pending_queue_item_if_match(item_id)
        session.close()


async def _delete_queue_item(item_id: int) -> None:
    global _shuffle_queue, _current_shuffle_index
    
    session = new_session()
    try:
        row = session.get(QueueItem, item_id)
        if row is not None:
            session.delete(row)
            session.commit()
            
            # Update shuffle queue if item was in it
            if _shuffle_enabled and item_id in _shuffle_queue:
                removed_index = _shuffle_queue.index(item_id)
                _shuffle_queue.remove(item_id)
                
                # Adjust current shuffle index if necessary
                if removed_index <= _current_shuffle_index:
                    _current_shuffle_index = max(0, _current_shuffle_index - 1)
    finally:
        session.close()

    _schedule_ts_description_update()

# Alias for backward compatibility
_remove_queue_item_internal = _delete_queue_item


async def _auto_play_next_from_queue(*, start_after_id: int | None = None) -> None:
    global _current_shuffle_index, _shuffle_queue
    
    session = new_session()
    try:
        if _shuffle_enabled and _shuffle_queue:
            # Play next shuffled track
            next_index = _current_shuffle_index + 1
            
            if next_index >= len(_shuffle_queue):
                if _repeat_mode == "all":
                    next_index = 0
                else:
                    return  # End of shuffled queue
            
            item_id = _shuffle_queue[next_index]
            _current_shuffle_index = next_index
        else:
            # Regular queue order
            cursor_id = start_after_id if start_after_id is not None else _current_queue_item_id
            if start_after_id is None and _current_queue_item_id and _repeat_mode == "one":
                # Repeat current track
                item_id = _current_queue_item_id
            else:
                # Get next track in regular order
                if cursor_id:
                    nxt = session.execute(
                        select(QueueItem)
                        .where(QueueItem.id > cursor_id)
                        .order_by(QueueItem.id.asc())
                        .limit(1)
                    ).scalars().first()
                else:
                    nxt = session.execute(
                        select(QueueItem)
                        .order_by(QueueItem.id.asc())
                        .limit(1)
                    ).scalars().first()
                
                if not nxt:
                    if _repeat_mode == "all":
                        # Loop back to beginning
                        nxt = session.execute(
                            select(QueueItem)
                            .order_by(QueueItem.id.asc())
                            .limit(1)
                        ).scalars().first()
                        if not nxt:
                            return
                    else:
                        return  # End of queue
                
                item_id = int(nxt.id)
    finally:
        session.close()

    await _play_queue_item_internal(item_id, requested_by="auto")


def _serialize_queue_item(row: QueueItem) -> dict:
    source_url = _strip_netease_queue_meta(row.source_url) if row.track_id.startswith("netease:") else row.source_url
    track_ref = _build_track_reference(str(row.track_id or ""))
    return {
        "id": row.id,
        "track_id": row.track_id,
        **track_ref,
        "title": row.title,
        "artist": row.artist,
        "album": row.album,
        "duration": row.duration / 1000.0 if row.duration else None,
        "artwork": row.cover_url,
        "source_url": source_url,
    }


def _build_track_reference(track_id: str) -> dict[str, object]:
    raw = str(track_id or "").strip()
    if not raw:
        return {"source": "unknown"}

    source, _, suffix = raw.partition(":")
    source = source.strip().lower() or "unknown"
    suffix = suffix.strip()

    payload: dict[str, object] = {"source": source}
    if source == "netease" and suffix:
        payload["song_id"] = suffix
    elif source == "qqmusic" and suffix:
        payload["song_mid"] = suffix
    elif source == "bilibili":
        video_id = _extract_bilibili_video_id(suffix or raw)
        if video_id:
            payload["video_id"] = video_id
            payload["webpage_url"] = _build_bilibili_video_url(video_id)
    return payload


def _serialize_history_item(row: HistoryItem) -> dict:
    return {
        "id": row.id,
        "played_at": row.played_at.isoformat(),
        "track_id": row.track_id,
        **_build_track_reference(str(row.track_id or "")),
        "title": row.title,
        "artist": row.artist,
        "album": row.album,
        "duration": row.duration / 1000.0 if row.duration else None,
        "artwork": row.cover_url,
        "source_url": row.source_url,
        "requested_by": row.requested_by,
    }


def _coerce_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _coerce_non_negative_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalize_netease_quality_level(value: object, *, default: str = "auto", strict: bool = False) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return default

    aliases = {
        "auto": "auto",
        "max": "auto",
        "highest": "auto",
        "standard": "standard",
        "higher": "higher",
        "exhigh": "exhigh",
        "lossless": "lossless",
        "hires": "hires",
        "hi-res": "hires",
        "jyeffect": "jyeffect",
        "sky": "sky",
        "dolby": "dolby",
        "jymaster": "jymaster",
        "master": "jymaster",
    }
    normalized = aliases.get(raw)
    if normalized is not None:
        return normalized

    if strict:
        supported = ", ".join(("auto",) + _NETEASE_QUALITY_LEVELS)
        raise HTTPException(status_code=400, detail=f"invalid netease level, supported: {supported}")
    return default


def _resolve_netease_request_level(level: str) -> str:
    normalized = _normalize_netease_quality_level(level, strict=True)
    if normalized == "auto":
        return "jymaster"
    return normalized


def _encode_netease_queue_source(level: str, source_url: str = "") -> str:
    normalized = _normalize_netease_quality_level(level, strict=False)
    resolved_source_url = str(source_url or "").strip()
    if normalized == "auto":
        return resolved_source_url
    if resolved_source_url:
        return f"{_NETEASE_QUEUE_META_PREFIX}{normalized}|{resolved_source_url}"
    return f"{_NETEASE_QUEUE_META_PREFIX}{normalized}"


def _encode_netease_queue_meta(level: str, source_url: str = "") -> str:
    # Keep the older helper name working while all call sites converge.
    return _encode_netease_queue_source(level, source_url)


def _extract_netease_queue_level(source_url: object) -> str:
    raw = str(source_url or "").strip()
    if raw.startswith(_NETEASE_QUEUE_META_PREFIX):
        level_raw, _, _rest = raw[len(_NETEASE_QUEUE_META_PREFIX) :].partition("|")
        return _normalize_netease_quality_level(level_raw, strict=False)
    return "auto"


def _strip_netease_queue_meta(source_url: object) -> str:
    raw = str(source_url or "").strip()
    if not raw.startswith(_NETEASE_QUEUE_META_PREFIX):
        return raw
    _level, sep, rest = raw[len(_NETEASE_QUEUE_META_PREFIX) :].partition("|")
    return rest.strip() if sep else ""


def _is_netease_queue_meta(source_url: object) -> bool:
    raw = str(source_url or "").strip()
    return raw.startswith(_NETEASE_QUEUE_META_PREFIX)


def _extract_netease_artist_names(song: dict) -> str:
    artists = (song.get("ar") or song.get("artists") or [])
    if not isinstance(artists, list):
        return ""
    names = [str((artist or {}).get("name") or "").strip() for artist in artists if isinstance(artist, dict)]
    return ", ".join([name for name in names if name])


def _extract_netease_album_fields(song: dict) -> tuple[str, str]:
    album = song.get("al") or song.get("album") or {}
    if isinstance(album, dict):
        return (
            str(album.get("name") or "").strip(),
            str(album.get("picUrl") or album.get("pic_url") or "").strip(),
        )
    if isinstance(album, str):
        return album.strip(), ""
    return "", ""


def _normalize_netease_song(song: dict) -> dict | None:
    song_id = str(song.get("id") or "").strip()
    if not song_id:
        return None

    album_name, artwork_url = _extract_netease_album_fields(song)
    duration_ms = _coerce_positive_int(song.get("dt") or song.get("duration"))
    return {
        "source": "netease",
        "track_id": f"netease:{song_id}",
        "song_id": song_id,
        "title": str(song.get("name") or song_id).strip(),
        "artist": _extract_netease_artist_names(song),
        "album": album_name,
        "duration_ms": duration_ms,
        "artwork_url": artwork_url,
    }


def _normalize_netease_search_items(data: dict) -> list[dict]:
    songs = (((data or {}).get("result") or {}).get("songs") or [])
    if not isinstance(songs, list):
        return []

    items: list[dict] = []
    for song in songs:
        if not isinstance(song, dict):
            continue
        normalized = _normalize_netease_song(song)
        if normalized is not None:
            items.append(normalized)
    return items


def _extract_qqmusic_artist_names(song: dict) -> str:
    artists = (song.get("singer") or song.get("artists") or [])
    if not isinstance(artists, list):
        return ""
    names = [str((artist or {}).get("name") or "").strip() for artist in artists if isinstance(artist, dict)]
    return ", ".join([name for name in names if name])


def _normalize_qqmusic_song(song: dict) -> dict | None:
    song_mid = str(song.get("mid") or song.get("songmid") or "").strip()
    if not song_mid:
        return None

    album = song.get("album") if isinstance(song.get("album"), dict) else {}
    album_mid = str((album or {}).get("mid") or song.get("albummid") or "").strip()
    album_name = str((album or {}).get("name") or song.get("albumname") or "").strip()
    interval = _coerce_positive_int(song.get("interval"))
    duration_ms = interval * 1000 if interval is not None else None
    artwork_url = qqmusic.get_song_cover_image(album_mid) if album_mid else ""

    return {
        "source": "qqmusic",
        "track_id": f"qqmusic:{song_mid}",
        "song_mid": song_mid,
        "title": str(song.get("name") or song_mid).strip(),
        "artist": _extract_qqmusic_artist_names(song),
        "album": album_name,
        "album_mid": album_mid,
        "duration_ms": duration_ms,
        "artwork_url": artwork_url,
    }


def _normalize_qqmusic_search_items(songs: list[dict]) -> list[dict]:
    items: list[dict] = []
    for song in songs:
        if not isinstance(song, dict):
            continue
        normalized = _normalize_qqmusic_song(song)
        if normalized is not None:
            items.append(normalized)
    return items


def _get_bilibili_download_lock(video_id: str) -> asyncio.Lock:
    lock = _bilibili_download_locks.get(video_id)
    if lock is None:
        lock = asyncio.Lock()
        _bilibili_download_locks[video_id] = lock
    return lock


def _clean_bilibili_text(value: object) -> str:
    text = unescape(str(value or "")).strip()
    if not text:
        return ""
    text = _BILIBILI_TAG_RE.sub("", text)
    return " ".join(text.split())


def _normalize_bilibili_artwork_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return f"https://{raw.lstrip('/')}"


def _normalize_bilibili_subtitle_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("http://"):
        return f"https://{raw[len('http://'):]}"
    if raw.startswith("https://"):
        return raw
    return f"https://{raw.lstrip('/')}"


def _count_bilibili_cjk_chars(value: str) -> int:
    return len(_BILIBILI_CJK_CHAR_RE.findall(value or ""))


def _count_bilibili_latin_chars(value: str) -> int:
    return len(_BILIBILI_LATIN_CHAR_RE.findall(value or ""))


def _infer_bilibili_subtitle_preference(*values: object) -> str:
    text = " ".join(_clean_bilibili_text(value) for value in values if str(value or "").strip())
    if not text:
        return "neutral"

    latin_count = _count_bilibili_latin_chars(text)
    cjk_count = _count_bilibili_cjk_chars(text)

    if latin_count >= max(6, cjk_count * 2):
        return "english"
    if cjk_count >= max(2, latin_count):
        return "chinese"
    return "neutral"


def _classify_bilibili_subtitle_language(meta: dict) -> str:
    tokens = " ".join(
        str(meta.get(key) or "").strip()
        for key in ("lan", "lan_doc", "lang", "language")
    )
    lower_tokens = tokens.lower()

    if any(token in tokens for token in ("中英", "双语", "双語")) or "bilingual" in lower_tokens:
        return "bilingual"
    if any(token in tokens for token in ("英文", "英语", "英語")):
        return "english"
    if any(token in tokens for token in ("中文", "汉语", "漢語", "普通话", "普通話", "国语", "國語")):
        return "chinese"
    if re.search(r"(^|[^a-z])en([^a-z]|$)", lower_tokens) or "english" in lower_tokens:
        return "english"
    if re.search(r"(^|[^a-z])(zh|cn|cmn)([^a-z]|$)", lower_tokens) or "chinese" in lower_tokens:
        return "chinese"
    return "unknown"


def _classify_bilibili_subtitle_content_language(lines: list[LyricLine]) -> str:
    if not lines:
        return "unknown"

    sample = " ".join(line.text for line in lines[:12]).strip()
    if not sample:
        return "unknown"

    latin_count = _count_bilibili_latin_chars(sample)
    cjk_count = _count_bilibili_cjk_chars(sample)

    if latin_count >= max(8, cjk_count * 2):
        return "english"
    if cjk_count >= max(4, latin_count * 2):
        return "chinese"
    if latin_count > 0 and cjk_count > 0:
        return "mixed"
    return "unknown"


def _score_bilibili_subtitle_candidate(candidate: dict, preference: str) -> float:
    score = 0.0
    language_hint = str(candidate.get("language_hint") or "unknown")
    content_language = str(candidate.get("content_language") or "unknown")
    is_auto = bool(candidate.get("is_auto"))
    line_count = _coerce_non_negative_int(candidate.get("line_count")) or 0
    order_index = _coerce_non_negative_int(candidate.get("order_index")) or 0

    if preference == "english":
        if language_hint == "english":
            score += 70
        elif language_hint == "bilingual":
            score += 35
        elif language_hint == "chinese":
            score -= 25

        if content_language == "english":
            score += 120
        elif content_language == "mixed":
            score += 30
        elif content_language == "chinese":
            score -= 50
    elif preference == "chinese":
        if language_hint == "chinese":
            score += 70
        elif language_hint == "bilingual":
            score += 30
        elif language_hint == "english":
            score -= 15

        if content_language == "chinese":
            score += 100
        elif content_language == "mixed":
            score += 25
        elif content_language == "english":
            score -= 25
    else:
        if content_language in {"english", "chinese"}:
            score += 20
        elif content_language == "mixed":
            score += 10
        if language_hint in {"english", "chinese", "bilingual"}:
            score += 10

    if is_auto:
        score -= 3
    else:
        score += 6

    score += min(line_count, 240) / 40.0
    score -= order_index * 0.1
    return score


def _parse_bilibili_subtitle_body_to_lines(body: list[dict]) -> list[LyricLine]:
    lyrics: list[LyricLine] = []
    for entry in body:
        if not isinstance(entry, dict):
            continue

        text = _clean_bilibili_text(
            str(entry.get("content") or entry.get("subtitle") or entry.get("text") or "").replace("\n", " / ")
        )
        if not text:
            continue

        raw_time = entry.get("from")
        if raw_time is None:
            raw_time = entry.get("start")

        try:
            time_s = float(raw_time)
        except (TypeError, ValueError):
            continue

        if not math.isfinite(time_s) or time_s < 0:
            continue

        if lyrics and abs(lyrics[-1].time - time_s) < 0.001 and lyrics[-1].text == text:
            continue

        lyrics.append(LyricLine(time=time_s, text=text))

    lyrics.sort(key=lambda line: line.time)
    return lyrics


def _parse_bilibili_duration_ms(value: object) -> int | None:
    if isinstance(value, (int, float)):
        seconds = int(float(value))
        return seconds * 1000 if seconds > 0 else None

    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        seconds = int(raw)
        return seconds * 1000 if seconds > 0 else None

    parts = raw.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if not numbers:
        return None

    seconds = 0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds * 1000 if seconds > 0 else None


def _extract_bilibili_video_id(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = _BILIBILI_VIDEO_ID_RE.search(raw)
    if not match:
        return ""
    token = match.group(1)
    if token.lower().startswith("bv"):
        return f"BV{token[2:]}"
    if token.lower().startswith("av"):
        return token.lower()
    return token


def _build_bilibili_video_url(video_id: str) -> str:
    raw = (video_id or "").strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.isdigit():
        raw = f"av{raw}"
    if raw.lower().startswith("av"):
        return f"https://www.bilibili.com/video/{raw.lower()}"
    if raw.lower().startswith("bv"):
        raw = f"BV{raw[2:]}"
    return f"https://www.bilibili.com/video/{raw}"


def _normalize_bilibili_search_item(item: dict) -> dict | None:
    video_id = _extract_bilibili_video_id(item.get("bvid") or item.get("arcurl") or item.get("aid"))
    if not video_id:
        return None

    aid = _coerce_positive_int(item.get("aid") or item.get("id"))
    normalized = {
        "source": "bilibili",
        "track_id": f"bilibili:{video_id}",
        "video_id": video_id,
        "title": _clean_bilibili_text(item.get("title")) or video_id,
        "artist": _clean_bilibili_text(item.get("author") or item.get("up_name") or ""),
        "album": _clean_bilibili_text(item.get("typename") or ""),
        "description": _clean_bilibili_text(item.get("description") or item.get("desc") or ""),
        "duration_ms": _parse_bilibili_duration_ms(item.get("duration")),
        "artwork_url": _normalize_bilibili_artwork_url(item.get("pic") or item.get("thumbnail")),
        "likes": _coerce_non_negative_int(item.get("like")),
        "favorites": _coerce_non_negative_int(item.get("favorites")),
        "coins": _coerce_non_negative_int(item.get("coins")),
        "webpage_url": _build_bilibili_video_url(video_id),
    }
    if aid is not None:
        normalized["id"] = aid
    return normalized


def _normalize_bilibili_search_items(items: list[dict]) -> list[dict]:
    normalized_items: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_bilibili_search_item(item)
        if normalized is not None:
            normalized_items.append(normalized)
    return normalized_items


def _normalize_bilibili_video_info(info: dict, *, fallback_video_id: str = "") -> dict | None:
    if not isinstance(info, dict):
        return None

    video_id = _extract_bilibili_video_id(
        info.get("bvid")
        or info.get("webpage_url")
        or info.get("original_url")
        or fallback_video_id
        or info.get("id")
    )
    if not video_id:
        return None

    categories = info.get("categories") or []
    category = ""
    if isinstance(categories, list) and categories:
        category = _clean_bilibili_text(categories[0])

    return {
        "source": "bilibili",
        "track_id": f"bilibili:{video_id}",
        "video_id": video_id,
        "title": _clean_bilibili_text(info.get("title")) or video_id,
        "artist": _clean_bilibili_text(
            info.get("uploader") or info.get("channel") or info.get("artist") or info.get("creator") or ""
        ),
        "album": category,
        "duration_ms": _parse_bilibili_duration_ms(info.get("duration")),
        "artwork_url": _normalize_bilibili_artwork_url(info.get("thumbnail")),
        "webpage_url": str(info.get("webpage_url") or _build_bilibili_video_url(video_id)).strip(),
    }


def _build_bilibili_api_params(video_id: str) -> dict[str, object]:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="invalid bilibili video_id")

    if normalized_video_id.lower().startswith("av"):
        aid = _coerce_positive_int(normalized_video_id[2:])
        if aid is None:
            raise HTTPException(status_code=400, detail="invalid bilibili aid")
        return {"aid": aid}
    return {"bvid": normalized_video_id}


def _build_bilibili_request_cookies(cookie: str | None = None) -> dict[str, str]:
    cookies = cookie_string_to_dict(str(cookie or "").strip())
    if not cookies.get("buvid3"):
        cookies["buvid3"] = f"{uuid.uuid4()}infoc"
    return cookies


def _request_bilibili_api_sync(
    path: str,
    params: dict[str, object],
    *,
    referer: str = "https://www.bilibili.com/",
    cookie: str | None = None,
) -> dict:
    headers = dict(_BILIBILI_DEFAULT_HEADERS)
    headers["referer"] = referer
    cookies = _build_bilibili_request_cookies(cookie)

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers, cookies=cookies) as client:
            resp = client.get(f"https://api.bilibili.com{path}", params=params)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"bilibili api request failed: path={path} error={exc}") from exc

    try:
        payload = resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"bilibili api returned invalid json: path={path}") from exc

    if int(payload.get("code") or 0) != 0:
        raise HTTPException(status_code=502, detail=f"bilibili api failed: path={path} code={payload.get('code')}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=f"bilibili api returned invalid data: path={path}")
    return data


def _fetch_bilibili_view_sync(video_id: str, *, cookie: str | None = None) -> dict:
    params = _build_bilibili_api_params(video_id)
    return _request_bilibili_api_sync(
        "/x/web-interface/wbi/view",
        params,
        referer=_build_bilibili_video_url(video_id),
        cookie=cookie,
    )


def _fetch_bilibili_nav_sync(cookie: str | None = None) -> dict:
    headers = dict(_BILIBILI_DEFAULT_HEADERS)
    headers["referer"] = "https://www.bilibili.com/"
    cookies = _build_bilibili_request_cookies(cookie)
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers, cookies=cookies) as client:
            resp = client.get("https://api.bilibili.com/x/web-interface/nav")
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"bilibili nav request failed: {exc}") from exc

    try:
        payload = resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="bilibili nav returned invalid json") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="bilibili nav returned invalid data")
    return data


def _resolve_bilibili_primary_cid(view_data: dict) -> int | None:
    cid = _coerce_positive_int(view_data.get("cid"))
    if cid is not None:
        return cid

    pages = view_data.get("pages") or []
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            cid = _coerce_positive_int(page.get("cid"))
            if cid is not None:
                return cid
    return None


def _normalize_bilibili_view_data(view_data: dict, *, fallback_video_id: str = "") -> dict | None:
    if not isinstance(view_data, dict):
        return None

    video_id = _extract_bilibili_video_id(view_data.get("bvid") or fallback_video_id)
    if not video_id:
        aid = _coerce_positive_int(view_data.get("aid"))
        if aid is not None:
            video_id = f"av{aid}"
    if not video_id:
        return None

    pages = view_data.get("pages") or []
    first_page = pages[0] if isinstance(pages, list) and pages and isinstance(pages[0], dict) else {}
    page_duration_s = _coerce_positive_int(first_page.get("duration"))
    total_duration_s = _coerce_positive_int(view_data.get("duration"))
    duration_ms = page_duration_s * 1000 if page_duration_s is not None else (
        total_duration_s * 1000 if total_duration_s is not None else None
    )

    owner = view_data.get("owner") if isinstance(view_data.get("owner"), dict) else {}
    category = _clean_bilibili_text(
        view_data.get("tname")
        or view_data.get("tname_v2")
        or view_data.get("parent_tname")
        or ""
    )

    return {
        "source": "bilibili",
        "track_id": f"bilibili:{video_id}",
        "video_id": video_id,
        "title": _clean_bilibili_text(view_data.get("title")) or video_id,
        "artist": _clean_bilibili_text((owner or {}).get("name") or ""),
        "album": category,
        "duration_ms": duration_ms,
        "artwork_url": _normalize_bilibili_artwork_url(view_data.get("pic")),
        "webpage_url": _build_bilibili_video_url(video_id),
    }


def _normalize_bilibili_view_summary(view_data: dict, *, fallback_video_id: str = "") -> dict | None:
    if not isinstance(view_data, dict):
        return None

    video_id = _extract_bilibili_video_id(view_data.get("bvid") or fallback_video_id)
    if not video_id:
        aid = _coerce_positive_int(view_data.get("aid"))
        if aid is not None:
            video_id = f"av{aid}"
    if not video_id:
        return None

    stat = view_data.get("stat") if isinstance(view_data.get("stat"), dict) else {}
    return {
        "video_id": video_id,
        "description": _clean_bilibili_text(view_data.get("desc") or ""),
        "likes": _coerce_non_negative_int(stat.get("like")),
        "favorites": _coerce_non_negative_int(stat.get("favorite")),
        "coins": _coerce_non_negative_int(stat.get("coin")),
    }


async def _fetch_bilibili_view_summary(video_id: str) -> dict | None:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        return None

    now = time.time()
    cached = _bilibili_view_summary_cache.get(normalized_video_id)
    if cached is not None and cached[0] > now:
        return dict(cached[1])

    async with _bilibili_view_summary_semaphore:
        now = time.time()
        cached = _bilibili_view_summary_cache.get(normalized_video_id)
        if cached is not None and cached[0] > now:
            return dict(cached[1])

        try:
            view_data = await asyncio.to_thread(_fetch_bilibili_view_sync, normalized_video_id)
            summary = _normalize_bilibili_view_summary(view_data, fallback_video_id=normalized_video_id)
        except HTTPException as exc:
            logger.warning("failed to fetch bilibili view summary for %s: %s", normalized_video_id, exc.detail)
            return None
        except Exception as exc:
            logger.warning("failed to fetch bilibili view summary for %s: %s", normalized_video_id, exc)
            return None

        if summary is None:
            return None

        _bilibili_view_summary_cache[normalized_video_id] = (
            time.time() + _BILIBILI_VIEW_SUMMARY_CACHE_TTL_S,
            dict(summary),
        )
        return summary


async def _enrich_bilibili_search_item(item: dict) -> dict:
    if not isinstance(item, dict):
        return item

    summary = await _fetch_bilibili_view_summary(str(item.get("video_id") or ""))
    if summary is None:
        return item

    enriched = dict(item)
    if summary.get("description"):
        enriched["description"] = summary["description"]
    for key in ("likes", "favorites", "coins"):
        value = summary.get(key)
        if value is not None:
            enriched[key] = value
    return enriched


async def _enrich_bilibili_search_items(items: list[dict]) -> list[dict]:
    if not items:
        return []
    return list(await asyncio.gather(*(_enrich_bilibili_search_item(item) for item in items)))


def _fetch_bilibili_playurl_sync(video_id: str, cid: int, *, dash: bool = False) -> dict:
    params = _build_bilibili_api_params(video_id)
    params.update({
        "cid": int(cid),
        "qn": 64,
        "fnver": 0,
        "fnval": 16 if dash else 0,
        "fourk": 0,
    })
    return _request_bilibili_api_sync("/x/player/playurl", params, referer=_build_bilibili_video_url(video_id))


def _fetch_bilibili_web_view_sync(video_id: str, *, cookie: str | None = None) -> dict:
    params = _build_bilibili_api_params(video_id)
    return _request_bilibili_api_sync(
        "/x/web-interface/view",
        params,
        referer=_build_bilibili_video_url(video_id),
        cookie=cookie,
    )


def _extract_bilibili_subtitle_catalog(player_data: dict) -> list[dict]:
    subtitle_data = player_data.get("subtitle") if isinstance(player_data.get("subtitle"), dict) else {}
    raw_subtitles = subtitle_data.get("subtitles") or subtitle_data.get("list") or []
    if not isinstance(raw_subtitles, list):
        return []

    subtitles: list[dict] = []
    for index, raw_subtitle in enumerate(raw_subtitles):
        if not isinstance(raw_subtitle, dict):
            continue

        subtitle_url = _normalize_bilibili_subtitle_url(
            raw_subtitle.get("subtitle_url") or raw_subtitle.get("url") or ""
        )
        if not subtitle_url:
            continue

        lan = str(raw_subtitle.get("lan") or "").strip()
        lan_doc = str(raw_subtitle.get("lan_doc") or raw_subtitle.get("lang") or "").strip()
        lowered_label = f"{lan} {lan_doc}".lower()
        subtitles.append(
            {
                "subtitle_url": subtitle_url,
                "lan": lan,
                "lan_doc": lan_doc,
                "order_index": index,
                "is_auto": lan.lower().startswith("ai-")
                or "自动" in lan_doc
                or "auto" in lowered_label,
            }
        )
    return subtitles


def _fetch_bilibili_player_subtitle_catalog_sync(
    video_id: str,
    *,
    aid: int,
    cid: int,
    cookie: str | None = None,
) -> list[dict]:
    referer = _build_bilibili_video_url(video_id)
    params = {"aid": int(aid), "cid": int(cid)}
    last_exc: HTTPException | None = None
    saw_success = False

    for path in ("/x/player/wbi/v2", "/x/player/v2"):
        try:
            player_data = _request_bilibili_api_sync(path, params, referer=referer, cookie=cookie)
        except HTTPException as exc:
            last_exc = exc
            logger.warning("failed to fetch bilibili subtitle catalog for %s via %s: %s", video_id, path, exc.detail)
            continue

        saw_success = True
        subtitles = _extract_bilibili_subtitle_catalog(player_data)
        if subtitles:
            return subtitles

    if not saw_success and last_exc is not None:
        raise last_exc
    return []


def _fetch_bilibili_subtitle_catalog_sync(video_id: str, *, cookie: str | None = None) -> list[dict]:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="invalid bilibili video_id")

    try:
        view_data = _fetch_bilibili_web_view_sync(normalized_video_id, cookie=cookie)
    except HTTPException:
        view_data = _fetch_bilibili_view_sync(normalized_video_id, cookie=cookie)

    aid = _coerce_positive_int(view_data.get("aid"))
    if aid is None and normalized_video_id.lower().startswith("av"):
        aid = _coerce_positive_int(normalized_video_id[2:])
    cid = _resolve_bilibili_primary_cid(view_data)
    if aid is None or cid is None:
        return []

    return _fetch_bilibili_player_subtitle_catalog_sync(normalized_video_id, aid=aid, cid=cid, cookie=cookie)


def _fetch_bilibili_subtitle_body_sync(subtitle_url: str, *, video_id: str, cookie: str | None = None) -> list[dict]:
    url = _normalize_bilibili_subtitle_url(subtitle_url)
    if not url:
        return []

    headers = dict(_BILIBILI_DEFAULT_HEADERS)
    headers["referer"] = _build_bilibili_video_url(video_id)
    cookies = _build_bilibili_request_cookies(cookie)
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers, cookies=cookies) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"bilibili subtitle request failed: {exc}") from exc

    try:
        payload = resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="bilibili subtitle returned invalid json") from exc

    body = payload.get("body") if isinstance(payload, dict) else None
    if not isinstance(body, list):
        return []
    return [entry for entry in body if isinstance(entry, dict)]


def _resolve_bilibili_lyrics_from_candidates_sync(
    video_id: str,
    subtitles: list[dict],
    *,
    title: str = "",
    artist: str = "",
    cookie: str | None = None,
) -> list[LyricLine]:
    if not subtitles:
        return []

    preference = _infer_bilibili_subtitle_preference(title, artist)
    candidates: list[dict] = []
    for subtitle in subtitles:
        body = subtitle.get("body") if isinstance(subtitle.get("body"), list) else None
        if body is None:
            try:
                body = _fetch_bilibili_subtitle_body_sync(
                    str(subtitle.get("subtitle_url") or ""),
                    video_id=video_id,
                    cookie=cookie,
                )
            except HTTPException as exc:
                logger.warning(
                    "failed to fetch bilibili subtitle for %s (%s): %s",
                    video_id,
                    subtitle.get("lan") or subtitle.get("lan_doc") or "unknown",
                    exc.detail,
                )
                continue

        lyrics = _parse_bilibili_subtitle_body_to_lines(body)
        if not lyrics:
            continue

        candidate = dict(subtitle)
        candidate["lyrics"] = lyrics
        candidate["line_count"] = len(lyrics)
        candidate["language_hint"] = _classify_bilibili_subtitle_language(candidate)
        candidate["content_language"] = _classify_bilibili_subtitle_content_language(lyrics)
        candidate["score"] = _score_bilibili_subtitle_candidate(candidate, preference)
        candidates.append(candidate)

    if not candidates:
        return []

    clean_title = _clean_bilibili_text(title)
    title_latin_count = _count_bilibili_latin_chars(clean_title)
    title_cjk_count = _count_bilibili_cjk_chars(clean_title)
    if title_latin_count >= 4:
        for candidate in candidates:
            if candidate.get("content_language") == "english":
                candidate["score"] = float(candidate.get("score") or 0.0) + 25.0
            elif candidate.get("language_hint") == "english":
                candidate["score"] = float(candidate.get("score") or 0.0) + 10.0
            elif candidate.get("content_language") == "chinese" and title_latin_count > title_cjk_count:
                candidate["score"] = float(candidate.get("score") or 0.0) - 10.0

    candidates.sort(
        key=lambda candidate: (
            float(candidate.get("score") or 0.0),
            len(candidate.get("lyrics") or []),
            -int(candidate.get("order_index") or 0),
        ),
        reverse=True,
    )
    return list(candidates[0].get("lyrics") or [])


def _fetch_bilibili_lyrics_sync(video_id: str, *, title: str = "", artist: str = "") -> list[LyricLine]:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="invalid bilibili video_id")

    subtitles = _fetch_bilibili_subtitle_catalog_sync(normalized_video_id)
    lyrics = _resolve_bilibili_lyrics_from_candidates_sync(
        normalized_video_id,
        subtitles,
        title=title,
        artist=artist,
    )
    if lyrics:
        return lyrics

    admin_cookie = _get_admin_bilibili_cookie_or_none()
    if admin_cookie:
        auth_subtitles = _fetch_bilibili_subtitle_catalog_sync(normalized_video_id, cookie=admin_cookie)
        lyrics = _resolve_bilibili_lyrics_from_candidates_sync(
            normalized_video_id,
            auth_subtitles,
            title=title,
            artist=artist,
            cookie=admin_cookie,
        )
        if lyrics:
            return lyrics

        playwright_candidates = asyncio.run(
            fetch_bilibili_subtitle_candidates_via_playwright(normalized_video_id, admin_cookie)
        )
        lyrics = _resolve_bilibili_lyrics_from_candidates_sync(
            normalized_video_id,
            playwright_candidates,
            title=title,
            artist=artist,
            cookie=admin_cookie,
        )
        if lyrics:
            return lyrics

    return []


async def _fetch_bilibili_lyrics(video_id: str, *, title: str = "", artist: str = "") -> list[LyricLine]:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        return []

    preference = _infer_bilibili_subtitle_preference(title, artist)
    admin_cookie = _get_admin_bilibili_cookie_or_none()
    auth_scope = "anon"
    if admin_cookie:
        auth_scope = hashlib.sha256(admin_cookie.encode("utf-8")).hexdigest()[:10]
    cache_key = f"{normalized_video_id}|{preference}|{auth_scope}"
    cached = _bilibili_subtitle_cache.get(cache_key)
    now = time.time()
    if cached is not None and cached[0] > now:
        return list(cached[1])

    try:
        lyrics = await asyncio.to_thread(
            _fetch_bilibili_lyrics_sync,
            normalized_video_id,
            title=title,
            artist=artist,
        )
    except HTTPException as exc:
        logger.warning("failed to resolve bilibili lyrics for %s: %s", normalized_video_id, exc.detail)
        return []
    except Exception as exc:
        logger.warning("failed to resolve bilibili lyrics for %s: %s", normalized_video_id, exc)
        return []

    _bilibili_subtitle_cache[cache_key] = (time.time() + _BILIBILI_SUBTITLE_CACHE_TTL_S, list(lyrics))
    return lyrics


def _extract_bilibili_playurl_download_target(playurl_data: dict) -> tuple[str, str]:
    dash = playurl_data.get("dash") or {}
    if isinstance(dash, dict):
        audios = dash.get("audio") or []
        if isinstance(audios, list) and audios:
            first = audios[0] if isinstance(audios[0], dict) else {}
            url = str((first or {}).get("baseUrl") or (first or {}).get("base_url") or "").strip()
            if url:
                return url, ".m4s"
            backup_urls = (first or {}).get("backupUrl") or (first or {}).get("backup_url") or []
            if isinstance(backup_urls, list) and backup_urls:
                backup = str(backup_urls[0] or "").strip()
                if backup:
                    return backup, ".m4s"

    durl = playurl_data.get("durl") or []
    if isinstance(durl, list) and durl:
        first = durl[0] if isinstance(durl[0], dict) else {}
        url = str((first or {}).get("url") or "").strip()
        if url:
            return url, ".mp4"
        backup_urls = (first or {}).get("backup_url") or []
        if isinstance(backup_urls, list) and backup_urls:
            backup = str(backup_urls[0] or "").strip()
            if backup:
                return backup, ".mp4"

    raise HTTPException(status_code=502, detail="bilibili playurl returned no downloadable media url")


async def _bilibili_search_videos(*, keywords: str, limit: int = 20, page: int = 1) -> dict:
    query = (keywords or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="keywords is empty")

    page = max(1, int(page))
    limit = max(1, min(int(limit), 50))
    params = {
        "Search_key": query,
        "keyword": query,
        "page": page,
        "page_size": limit,
        "context": "",
        "duration": 0,
        "tids_2": "",
        "__refresh__": "true",
        "search_type": "video",
        "tids": 0,
        "highlight": 1,
    }
    cookies = {"buvid3": f"{uuid.uuid4()}infoc"}

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://api.bilibili.com/x/web-interface/search/type",
                params=params,
                headers=_BILIBILI_DEFAULT_HEADERS,
                cookies=cookies,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"bilibili search request failed: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"bilibili search failed: status={resp.status_code}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="bilibili search returned invalid json") from exc

    if int(payload.get("code") or 0) != 0:
        raise HTTPException(status_code=502, detail=f"bilibili search failed: code={payload.get('code')}")

    data = payload.get("data") or {}
    raw_items = data.get("result") or []
    items = _normalize_bilibili_search_items(raw_items if isinstance(raw_items, list) else [])
    items = await _enrich_bilibili_search_items(items)
    total = _coerce_positive_int(data.get("numResults"))
    num_pages = _coerce_positive_int(data.get("numPages"))
    return {
        "source": "bilibili",
        "keywords": query,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": num_pages,
        "has_more": page < num_pages if num_pages is not None else len(items) == limit,
        "items": items,
    }


def _get_yt_dlp_module():
    try:
        import yt_dlp  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="yt-dlp is not installed on backend") from exc
    return yt_dlp


def _find_cached_bilibili_audio(video_id: str) -> str:
    if not BILIBILI_AUDIO_DIR.exists():
        return ""

    requested_paths = set(BILIBILI_AUDIO_DIR.glob(f"{video_id}.*"))
    prune_result = prune_audio_cache(
        BILIBILI_AUDIO_DIR,
        max_bytes=BILIBILI_AUDIO_CACHE_MAX_BYTES,
        ttl_seconds=BILIBILI_AUDIO_CACHE_TTL_SECONDS,
        partial_ttl_seconds=BILIBILI_AUDIO_PARTIAL_TTL_SECONDS,
        protected_paths=requested_paths,
    )
    if prune_result.removed_files:
        logger.info(
            "pruned %s Bilibili audio cache files (%s bytes)",
            prune_result.removed_files,
            prune_result.removed_bytes,
        )

    candidates: list[Path] = []
    for path in BILIBILI_AUDIO_DIR.glob(f"{video_id}.*"):
        if not path.is_file():
            continue
        if path.name.endswith(".part"):
            continue
        candidates.append(path)
    extension_priority = {
        ".m4a": 0,
        ".m4s": 1,
        ".aac": 2,
        ".mp3": 3,
        ".ogg": 4,
        ".opus": 5,
        ".wav": 6,
        ".flac": 7,
        ".mp4": 20,
        ".mkv": 21,
        ".webm": 22,
    }
    candidates.sort(key=lambda path: (extension_priority.get(path.suffix.lower(), 100), path.name))
    if not candidates:
        return ""
    selected = candidates[0]
    try:
        selected.touch()
    except OSError:
        pass
    return str(selected.resolve())


def _extract_bilibili_video_info_sync(video_id: str) -> dict:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="invalid bilibili video_id")

    api_error: Exception | None = None
    try:
        view_data = _fetch_bilibili_view_sync(normalized_video_id)
        normalized = _normalize_bilibili_view_data(view_data, fallback_video_id=normalized_video_id)
        if normalized is not None:
            return normalized
    except Exception as exc:
        api_error = exc

    yt_dlp = _get_yt_dlp_module()
    url = _build_bilibili_video_url(normalized_video_id)
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": _BILIBILI_DEFAULT_HEADERS,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    normalized = _normalize_bilibili_video_info(info, fallback_video_id=normalized_video_id)
    if normalized is None:
        if api_error is not None:
            raise RuntimeError(f"failed to parse bilibili metadata via api ({api_error}) and yt-dlp fallback")
        raise RuntimeError("failed to parse bilibili metadata")
    return normalized


async def _extract_bilibili_video_info(video_id: str) -> dict:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="invalid bilibili video_id")

    try:
        normalized = await asyncio.to_thread(_extract_bilibili_video_info_sync, normalized_video_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to resolve bilibili video: {exc}") from exc

    if not isinstance(normalized, dict):
        raise HTTPException(status_code=502, detail="failed to parse bilibili video metadata")
    return normalized


def _download_bilibili_audio_sync(video_id: str) -> tuple[str, dict | None]:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="invalid bilibili video_id")

    BILIBILI_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    api_error: Exception | None = None
    try:
        view_data = _fetch_bilibili_view_sync(normalized_video_id)
        metadata = _normalize_bilibili_view_data(view_data, fallback_video_id=normalized_video_id)
        cid = _resolve_bilibili_primary_cid(view_data)
        if cid is None:
            raise HTTPException(status_code=502, detail="bilibili view api returned no cid")

        playurl_data = _fetch_bilibili_playurl_sync(normalized_video_id, cid, dash=True)
        download_url, suffix = _extract_bilibili_playurl_download_target(playurl_data)
        output_path = BILIBILI_AUDIO_DIR / f"{normalized_video_id}{suffix}"
        tmp_path = output_path.with_name(f"{output_path.name}.part")

        headers = dict(_BILIBILI_DEFAULT_HEADERS)
        headers["referer"] = _build_bilibili_video_url(normalized_video_id)
        with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
            with client.stream("GET", download_url) as resp:
                resp.raise_for_status()
                with open(tmp_path, "wb") as fh:
                    for chunk in resp.iter_bytes():
                        if chunk:
                            fh.write(chunk)
        os.replace(tmp_path, output_path)
        return str(output_path.resolve()), metadata
    except Exception as exc:
        api_error = exc

    yt_dlp = _get_yt_dlp_module()
    outtmpl = str(BILIBILI_AUDIO_DIR / f"{normalized_video_id}.%(ext)s")
    url = _build_bilibili_video_url(normalized_video_id)
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "overwrites": False,
        "continuedl": True,
        "retries": 2,
        "fragment_retries": 2,
        "http_headers": _BILIBILI_DEFAULT_HEADERS,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        if api_error is not None:
            raise RuntimeError(f"bilibili api download failed ({api_error}); yt-dlp fallback failed ({exc})") from exc
        raise

    filepath = _find_cached_bilibili_audio(normalized_video_id)
    normalized = _normalize_bilibili_video_info(info, fallback_video_id=normalized_video_id)
    return filepath, normalized


async def _download_bilibili_audio(video_id: str) -> tuple[str, dict | None]:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="invalid bilibili video_id")

    lock = _get_bilibili_download_lock(normalized_video_id)
    async with lock:
        cached_path = _find_cached_bilibili_audio(normalized_video_id)
        if cached_path:
            return cached_path, None

        try:
            filepath, metadata = await asyncio.to_thread(_download_bilibili_audio_sync, normalized_video_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"failed to download bilibili audio: {exc}") from exc

        if not filepath:
            raise HTTPException(status_code=502, detail="failed to locate downloaded bilibili audio")
        return filepath, metadata


async def _resolve_bilibili_playback_payload(
    *,
    video_id: str,
    artist: str = "",
    album: str = "",
    artwork_url: str = "",
    duration_ms: int | None = None,
) -> tuple[str, int | None, str, str, str]:
    normalized_video_id = _extract_bilibili_video_id(video_id)
    if not normalized_video_id:
        raise HTTPException(status_code=400, detail="invalid bilibili video_id")

    local_path, metadata = await _download_bilibili_audio(normalized_video_id)
    needs_metadata = not artist or not album or not artwork_url or duration_ms is None
    if metadata is None and needs_metadata:
        metadata = await _extract_bilibili_video_info(normalized_video_id)

    resolved_duration_ms = _coerce_positive_int(duration_ms)
    if resolved_duration_ms is None and metadata is not None:
        resolved_duration_ms = _coerce_positive_int(metadata.get("duration_ms"))

    resolved_artist = (artist or str((metadata or {}).get("artist") or "")).strip()
    resolved_album = (album or str((metadata or {}).get("album") or "")).strip()
    resolved_artwork_url = (artwork_url or str((metadata or {}).get("artwork_url") or "")).strip()
    return local_path, resolved_duration_ms, resolved_artist, resolved_album, resolved_artwork_url


@app.get("/voice/status")
async def voice_status() -> dict:
    st = await voice.get_status()

    state_map = {
        "STATE_IDLE": "idle",
        "STATE_PLAYING": "playing",
        "STATE_PAUSED": "paused",
        "STATE_BUFFERING": "buffering",
        "STATE_ERROR": "error",
        "STATE_UNSPECIFIED": "idle",
    }
    state = state_map.get(str(st.state or "").strip().upper(), "idle")

    async with _playback_lock:
        qid = _current_queue_item_id
        started_at = _play_started_at
        paused_at = _paused_at
        paused_total_s = _paused_total_s
        duration_ms = _current_duration_ms
        cached_artist = _current_artist
        cached_album = _current_album
        cached_artwork_url = _current_artwork_url

    # If backend has no notion of current track, treat as idle.
    if qid is None:
        state = "idle"

    current_time_s = 0.0
    if started_at is not None and qid is not None:
        current_time_s = _resolve_playback_position_s(
            now_s=time.monotonic(),
            started_at=started_at,
            paused_at=paused_at,
            paused_total_s=paused_total_s,
        )
        if paused_at is not None:
            state = "paused"

    if duration_ms > 0:
        current_time_s = min(current_time_s, duration_ms / 1000.0)

    now_playing_artist = (cached_artist or "").strip()
    now_playing_album = (cached_album or "").strip()
    artwork_url = (cached_artwork_url or "").strip()
    if qid is not None and not now_playing_artist:
        session = new_session()
        try:
            row = session.get(QueueItem, int(qid))
            if row is not None:
                now_playing_artist = str(row.artist or "")
        finally:
            session.close()

    return {
        "state": state,
        "now_playing_title": st.now_playing_title,
        "now_playing_source_url": st.now_playing_source_url,
        "now_playing_artist": now_playing_artist,
        "now_playing_album": now_playing_album,
        "artwork_url": artwork_url,
        "track_id": qid,
        "current_time": current_time_s,
        "duration": (duration_ms / 1000.0) if duration_ms > 0 else 0.0,
        "volume_percent": st.volume_percent,
        "is_shuffled": _shuffle_enabled,
        "repeat_mode": _repeat_mode,
    }


@app.put("/voice/volume")
async def set_voice_volume(
    req: VolumeUpdateRequest,
    session: Session = Depends(get_session),
) -> dict:
    v = int(req.volume_percent)
    if v < 0:
        v = 0
    if v > 200:
        v = 200

    await voice.set_volume(v)

    row = session.get(Secret, "voice_volume")
    if not row:
        row = Secret(key="voice_volume", value=str(v))
        session.add(row)
    else:
        row.value = str(v)
    session.commit()
    return {"ok": True, "volume_percent": v}


@app.get("/voice/fx")
async def get_voice_fx() -> dict:
    fx = await voice.get_audio_fx()
    return {
        "pan": fx.pan,
        "width": fx.width,
        "swap_lr": fx.swap_lr,
        "bass_db": fx.bass_db,
        "reverb_mix": fx.reverb_mix,
    }


@app.put("/voice/fx")
async def set_voice_fx(req: AudioFxUpdateRequest) -> dict:
    await voice.set_audio_fx(
        pan=req.pan,
        width=req.width,
        swap_lr=req.swap_lr,
        bass_db=req.bass_db,
        reverb_mix=req.reverb_mix,
    )
    fx = await voice.get_audio_fx()
    return {
        "ok": True,
        "pan": fx.pan,
        "width": fx.width,
        "swap_lr": fx.swap_lr,
        "bass_db": fx.bass_db,
        "reverb_mix": fx.reverb_mix,
    }


@app.post("/voice/play")
async def voice_play() -> dict:
    st = await voice.get_status()
    cur = str(st.state or "").strip().upper()
    if cur == "STATE_IDLE":
        async with _playback_lock:
            pending_item_id = _pending_queue_item_id
        if pending_item_id is not None:
            return {"ok": True, "action": "pending"}
        await _auto_play_next_from_queue()
        return {"ok": True, "action": "play_next"}
    if cur == "STATE_PAUSED":
        await _mark_playback_resumed()
        await voice.resume()
        return {"ok": True, "action": "resume"}
    # STATE_PLAYING or unknown — sync state and report
    async with _playback_lock:
        active = _current_queue_item_id or _pending_queue_item_id
    title = (st.now_playing_title or "").strip()
    return {
        "ok": True,
        "action": "already_playing",
        "state": cur,
        "title": title,
        "backend_item_id": active,
    }


@app.post("/voice/pause")
async def voice_pause() -> dict:
    await _mark_playback_paused()
    await voice.pause()
    return {"ok": True}


@app.post("/voice/next")
async def voice_next() -> dict:
    global _current_shuffle_index, _shuffle_queue
    current_item_id = None
    pending_item_id = None
    async with _playback_lock:
        current_item_id = _current_queue_item_id
        pending_item_id = _pending_queue_item_id

    active_item_id = current_item_id or pending_item_id

    if active_item_id:
        await _remove_queue_item_internal(active_item_id)
    await _invalidate_play_requests()

    if _shuffle_enabled and _shuffle_queue:
        # Handle shuffled next
        next_index = _current_shuffle_index + 1
        
        if next_index >= len(_shuffle_queue):
            if _repeat_mode == "all":
                next_index = 0
            else:
                await _set_now_playing_queue_item(None)
                await voice.skip()
                return {"ok": True, "action": "end_of_queue"}
        
        item_id = _shuffle_queue[next_index]
        _current_shuffle_index = next_index
        
        await _play_queue_item_internal(item_id, requested_by="next")
        return {"ok": True, "action": "play_shuffled_next"}
    else:
        # Regular next behavior - just play next without removing current
        start_after_id = active_item_id
        await _set_now_playing_queue_item(None)
        await voice.skip()
        await _auto_play_next_from_queue(start_after_id=start_after_id)
        return {"ok": True, "action": "next"}


@app.post("/voice/skip")
async def voice_skip() -> dict:
    """Skip current song: remove from queue and play next"""
    global _current_shuffle_index, _shuffle_queue
    
    # Get current playing item to remove it
    current_item_id = None
    pending_item_id = None
    async with _playback_lock:
        current_item_id = _current_queue_item_id
        pending_item_id = _pending_queue_item_id

    active_item_id = current_item_id or pending_item_id
    
    if active_item_id:
        # Remove current song from queue
        await _remove_queue_item_internal(active_item_id)
        await _invalidate_play_requests()
        
        # Stop current playback
        await _set_now_playing_queue_item(None)
        await voice.skip()
        
        # Auto play next song
        await _auto_play_next_from_queue(start_after_id=active_item_id)
        return {"ok": True, "action": "skipped_and_next", "removed_track_id": active_item_id}
    else:
        await _invalidate_play_requests()
        return {"ok": True, "action": "no_current_track", "message": "当前没有正在播放的歌曲"}


@app.post("/voice/previous")
async def voice_previous() -> dict:
    global _current_shuffle_index, _shuffle_queue
    
    if _shuffle_enabled and _shuffle_queue:
        # Handle shuffled previous
        prev_index = _current_shuffle_index - 1
        
        if prev_index < 0:
            if _repeat_mode == "all":
                prev_index = len(_shuffle_queue) - 1
            else:
                return {"ok": True, "message": "Beginning of shuffled queue"}
        
        item_id = _shuffle_queue[prev_index]
        _current_shuffle_index = prev_index
        
        await _play_queue_item_internal(item_id, requested_by="previous")
        return {"ok": True, "action": "play_shuffled_previous"}
    else:
        # Handle regular previous
        session = new_session()
        try:
            async with _playback_lock:
                cursor_item_id = _current_queue_item_id or _pending_queue_item_id

            if cursor_item_id:
                prev = session.execute(
                    select(QueueItem)
                    .where(QueueItem.id < cursor_item_id)
                    .order_by(QueueItem.id.desc())
                    .limit(1)
                ).scalars().first()
                
                if prev:
                    await _play_queue_item_internal(int(prev.id), requested_by="previous")
                    return {"ok": True, "action": "play_previous"}
                elif _repeat_mode == "all":
                    # Go to last track
                    last = session.execute(
                        select(QueueItem)
                        .order_by(QueueItem.id.desc())
                        .limit(1)
                    ).scalars().first()
                    
                    if last:
                        await _play_queue_item_internal(int(last.id), requested_by="previous")
                        return {"ok": True, "action": "play_last"}
        finally:
            session.close()
        
        return {"ok": True, "message": "No previous track available"}


class SeekRequest(BaseModel):
    time: float


class LyricLine(BaseModel):
    time: float
    text: str


class LyricsResponse(BaseModel):
    lyrics: list[LyricLine]


@app.post("/voice/seek")
async def voice_seek(req: SeekRequest) -> dict:
    if not math.isfinite(req.time):
        raise HTTPException(status_code=400, detail="invalid seek time")

    async with _playback_lock:
        has_track = _current_queue_item_id is not None and bool(_current_source_url)
        duration_ms = int(_current_duration_ms or 0)

    if not has_track:
        raise HTTPException(status_code=400, detail="当前没有正在播放的歌曲")

    target_time_s = max(0.0, float(req.time))
    if duration_ms > 0:
        target_time_s = min(target_time_s, duration_ms / 1000.0)

    try:
        await voice.seek(target_time_s)
    except RuntimeError as e:
        detail = str(e) or "seek failed"
        if "no active playback" in detail.lower():
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=500, detail=detail)

    await _mark_playback_seeked(target_time_s)
    return {"ok": True, "time": target_time_s}


class ShuffleRequest(BaseModel):
    enabled: bool


@app.post("/voice/shuffle")
async def voice_shuffle(req: ShuffleRequest) -> dict:
    global _shuffle_enabled, _shuffle_queue, _current_shuffle_index
    
    _shuffle_enabled = req.enabled
    
    if _shuffle_enabled:
        # Generate shuffled queue from current queue
        session = new_session()
        try:
            queue_items = session.execute(select(QueueItem).order_by(QueueItem.id.asc())).scalars().all()
            queue_ids = [item.id for item in queue_items]
            
            # Shuffle the queue IDs using Fisher-Yates algorithm
            import random
            _shuffle_queue = queue_ids.copy()
            for i in range(len(_shuffle_queue) - 1, 0, -1):
                j = random.randint(0, i)
                _shuffle_queue[i], _shuffle_queue[j] = _shuffle_queue[j], _shuffle_queue[i]
            
            # Find current track position in shuffled queue
            if _current_queue_item_id:
                try:
                    _current_shuffle_index = _shuffle_queue.index(_current_queue_item_id)
                except ValueError:
                    _current_shuffle_index = -1
            else:
                _current_shuffle_index = -1
        finally:
            session.close()
    else:
        _shuffle_queue = []
        _current_shuffle_index = -1
    
    _schedule_ts_description_update()
    return {"ok": True, "enabled": _shuffle_enabled}


class RepeatRequest(BaseModel):
    mode: str  # "none", "all", "one"


@app.post("/voice/repeat")
async def voice_repeat(req: RepeatRequest) -> dict:
    global _repeat_mode
    
    if req.mode in ["none", "all", "one"]:
        _repeat_mode = req.mode
    else:
        _repeat_mode = "none"
    
    _schedule_ts_description_update()
    return {"ok": True, "mode": _repeat_mode}


@app.get("/search", response_model=SearchResponse)
async def search(keywords: str, limit: int = 20, offset: int = 0) -> SearchResponse:
    data = await netease.search(keywords=keywords, limit=limit, offset=offset)
    try:
        songs = (((data or {}).get("result") or {}).get("songs") or [])
        if isinstance(songs, list) and songs:
            ids = [str((s or {}).get("id") or "").strip() for s in songs if isinstance(s, dict)]
            ids = [i for i in ids if i]
            if ids:
                detail = await netease.song_detail(song_id=",".join(ids))
                dsongs = (detail or {}).get("songs") or []
                by_id: dict[str, dict] = {}
                if isinstance(dsongs, list):
                    for d in dsongs:
                        if not isinstance(d, dict):
                            continue
                        sid = str(d.get("id") or "").strip()
                        if sid:
                            by_id[sid] = d

                for s in songs:
                    if not isinstance(s, dict):
                        continue
                    sid = str(s.get("id") or "").strip()
                    if not sid:
                        continue
                    d = by_id.get(sid)
                    if not d:
                        continue

                    al = d.get("al") or {}
                    if isinstance(al, dict):
                        pic = al.get("picUrl") or al.get("pic_url")
                        name = al.get("name")
                        if pic:
                            album = s.get("album")
                            if isinstance(album, dict):
                                if not album.get("picUrl"):
                                    album["picUrl"] = pic
                                if name and not album.get("name"):
                                    album["name"] = name
                            else:
                                s["album"] = {"picUrl": pic, "name": name or ""}

                            al2 = s.get("al")
                            if isinstance(al2, dict):
                                if not al2.get("picUrl"):
                                    al2["picUrl"] = pic
                                if name and not al2.get("name"):
                                    al2["name"] = name
                            else:
                                s["al"] = {"picUrl": pic, "name": name or ""}
                        else:
                            if name:
                                album = s.get("album")
                                if isinstance(album, dict) and not album.get("name"):
                                    album["name"] = name
                                al2 = s.get("al")
                                if isinstance(al2, dict) and not al2.get("name"):
                                    al2["name"] = name

                    ar = d.get("ar") or []
                    if isinstance(ar, list) and ar:
                        if not s.get("ar"):
                            s["ar"] = ar
                        if not s.get("artists"):
                            s["artists"] = ar
    except Exception:
        pass
    return SearchResponse(raw=data)


def _parse_lrc_to_lines(lrc: str) -> list[LyricLine]:
    lines: list[LyricLine] = []
    for raw in (lrc or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if not s.startswith("["):
            continue
        parts = s.split("]")
        if len(parts) < 2:
            continue
        text = "]".join(parts[1:]).strip()
        for tag in parts[:-1]:
            t = tag.lstrip("[").strip()
            if not t:
                continue
            if ":" not in t:
                continue
            mm, rest = t.split(":", 1)
            try:
                minutes = int(mm)
            except ValueError:
                continue
            try:
                seconds = float(rest)
            except ValueError:
                continue
            ts = minutes * 60.0 + seconds
            lines.append(LyricLine(time=ts, text=text))
    lines.sort(key=lambda x: x.time)
    return lines


@app.get("/lyrics/{queue_item_id}", response_model=LyricsResponse)
async def lyrics(queue_item_id: int) -> LyricsResponse:
    session = new_session()
    try:
        item = session.get(QueueItem, queue_item_id)
        if not item:
            raise HTTPException(status_code=404, detail="not found")
        track_id = str(item.track_id or "")
        title = str(item.title or "")
        artist = str(item.artist or "")
    finally:
        session.close()

    if track_id.startswith("netease:"):
        # 网易云音乐歌词
        song_id = track_id.split(":", 1)[1]
        cookie = None
        try:
            # Prefer admin cookie to reduce rate limit / restricted lyrics.
            session2 = new_session()
            try:
                cookie = _get_admin_cookie(session2)
            finally:
                session2.close()
        except Exception:
            cookie = None

        data = await netease.lyric(song_id=song_id, cookie=cookie)
        lrc = (((data or {}).get("lrc") or {}).get("lyric") or "")
        return LyricsResponse(lyrics=_parse_lrc_to_lines(str(lrc)))
    
    elif track_id.startswith("qqmusic:"):
        # QQ 音乐歌词
        song_mid = track_id.split(":", 1)[1]
        try:
            # 设置 QQ 音乐 admin cookie
            session2 = new_session()
            try:
                cookie = _get_admin_qqmusic_cookie(session2)
                qqmusic.set_cookie(cookie)
            finally:
                session2.close()
            
            # 获取 QQ 音乐歌词
            data = await qqmusic.get_song_lyric(song_mid)
            lrc = data.get("lyric", "") if data else ""
            return LyricsResponse(lyrics=_parse_lrc_to_lines(str(lrc)))
        except Exception:
            return LyricsResponse(lyrics=[])

    elif track_id.startswith("bilibili:"):
        video_id = _extract_bilibili_video_id(track_id.split(":", 1)[1])
        if not video_id:
            return LyricsResponse(lyrics=[])
        lyrics = await _fetch_bilibili_lyrics(video_id, title=title, artist=artist)
        return LyricsResponse(lyrics=lyrics)
    
    else:
        return LyricsResponse(lyrics=[])


@app.get("/playlist/detail")
async def playlist_detail(id: str, request: Request) -> dict:
    cookie = request.headers.get("x-netease-cookie")
    return await netease.playlist_detail(playlist_id=id, cookie=cookie)


@app.get("/netease/qr/key")
async def netease_qr_key() -> dict:
    return await netease.qr_key()


@app.get("/netease/qr/create")
async def netease_qr_create(key: str) -> dict:
    return await netease.qr_create(key)


@app.get("/netease/qr/check")
async def netease_qr_check(key: str) -> dict:
    return await netease.qr_check(key)


def _extract_netease_song_url_item(data: dict) -> dict:
    code = (data or {}).get("code")
    if code not in (None, 200):
        raise HTTPException(status_code=502, detail=f"netease api error: code={code}")

    items = (data or {}).get("data") or []
    if not items:
        raise HTTPException(status_code=502, detail="netease api error: empty data")

    return (items[0] or {}) if isinstance(items, list) else {}


def _resolve_netease_song_url(data: dict) -> str:
    it = _extract_netease_song_url_item(data)
    url = (it or {}).get("url") or ""
    if url:
        return url

    item_code = (it or {}).get("code")
    if item_code not in (None, 200):
        if item_code == 404:
            raise HTTPException(status_code=404, detail="netease track not found (song removed/unavailable)")
        if item_code == -110:
            raise HTTPException(status_code=503, detail="netease temporarily unavailable (code=-110), please retry")
        raise HTTPException(status_code=403, detail=f"netease track unavailable: code={item_code}")

    fee = (it or {}).get("fee")
    payed = (it or {}).get("payed")
    level = (it or {}).get("level")

    if fee in (1, 4) or level == "vip" or (isinstance(payed, int) and payed > 0):
        raise HTTPException(status_code=402, detail="netease track requires VIP/paid account")

    raise HTTPException(status_code=403, detail="netease track not playable (no copyright/region restricted)")


def _resolve_netease_song_url_level(data: dict) -> str:
    item = _extract_netease_song_url_item(data)
    return str((item or {}).get("level") or "").strip()


def _resolve_netease_song_url_br(data: dict) -> int | None:
    item = _extract_netease_song_url_item(data)
    return _coerce_positive_int((item or {}).get("br"))


def _resolve_netease_duration_ms(detail: dict) -> int | None:
    songs = (detail or {}).get("songs") or []
    if not songs or not isinstance(songs, list):
        return None
    dt = (songs[0] or {}).get("dt")
    if isinstance(dt, int) and dt > 0:
        return dt
    return None


def _resolve_netease_album_and_artwork(detail: dict) -> tuple[str, str]:
    songs = (detail or {}).get("songs") or []
    if not songs or not isinstance(songs, list):
        return "", ""
    s0 = songs[0] or {}
    al = s0.get("al") or {}
    if not isinstance(al, dict):
        return "", ""
    album = str(al.get("name") or "")
    artwork_url = str(al.get("picUrl") or al.get("pic_url") or "")
    return album, artwork_url


def _cookie_fingerprint(cookie: str) -> dict:
    c = (cookie or "").encode("utf-8")
    h = hashlib.sha256(c).hexdigest()
    return {
        "len": len(c),
        "sha256": h,
    }


def _cookie_key_fingerprint() -> dict:
    k = (settings.cookie_key or "").encode("utf-8")
    return {
        "len": len(k),
        "sha256": hashlib.sha256(k).hexdigest(),
    }


async def _netease_notice_if_trial(song_id: str, cookie: str) -> str:
    notice, _dt, _artist, _album, _artwork = await _netease_notice_and_duration(song_id, cookie)
    return notice


async def _netease_notice_and_duration(song_id: str, cookie: str) -> tuple[str, int | None, str, str, str]:
    detail = await netease.song_detail(song_id=song_id, cookie=cookie)
    dt = _resolve_netease_duration_ms(detail)
    meta = _extract_song_meta_from_detail(detail, song_id)
    artist = ""
    if meta is not None:
        _title, artist = meta
    album, artwork_url = _resolve_netease_album_and_artwork(detail)
    if dt is not None and dt <= 30_000:
        return "该曲为试听版(≤30秒)，可能需要会员", dt, artist, album, artwork_url
    return "", dt, artist, album, artwork_url


def _netease_notice_for_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return ""
    if int(duration_ms) <= 0:
        return ""
    if int(duration_ms) <= 30_000:
        return "该曲为试听版(≤30秒)，可能需要会员"
    return ""


async def _resolve_netease_playback_payload(
    *,
    song_id: str,
    cookie: str,
    artist: str = "",
    album: str = "",
    artwork_url: str = "",
    duration_ms: int | None = None,
    quality_level: str = "auto",
) -> tuple[str, bool, str, int | None, str, str, str]:
    resolved_artist = (artist or "").strip()
    resolved_album = (album or "").strip()
    resolved_artwork_url = (artwork_url or "").strip()
    resolved_duration_ms = int(duration_ms) if duration_ms is not None and int(duration_ms) > 0 else None
    notice = _netease_notice_for_duration(resolved_duration_ms)

    if resolved_duration_ms is None or not resolved_artist or not resolved_album or not resolved_artwork_url:
        detail_notice, detail_duration_ms, detail_artist, detail_album, detail_artwork_url = await _netease_notice_and_duration(song_id, cookie)
        if resolved_duration_ms is None:
            resolved_duration_ms = detail_duration_ms
        if detail_artist and not resolved_artist:
            resolved_artist = detail_artist
        if detail_album and not resolved_album:
            resolved_album = detail_album
        if detail_artwork_url and not resolved_artwork_url:
            resolved_artwork_url = detail_artwork_url
        if detail_notice:
            notice = detail_notice
        elif not notice:
            notice = _netease_notice_for_duration(resolved_duration_ms)

    requested_level = _resolve_netease_request_level(quality_level)
    data = await netease.song_url_v1(song_id=song_id, cookie=cookie, level=requested_level)
    trial = False
    try:
        url = _resolve_netease_song_url(data)
    except HTTPException as e:
        if e.status_code == 402:
            trial_data = await netease.song_url(song_id=song_id, cookie=cookie, br=128000)
            url = _resolve_netease_song_url(trial_data)
            trial = True
        else:
            raise

    return url, trial, notice, resolved_duration_ms, resolved_artist, resolved_album, resolved_artwork_url


@app.get("/netease/song/url")
async def song_url(id: str, level: str = "auto", session: Session = Depends(get_session)) -> dict:
    cookie = _get_admin_cookie(session)
    requested_level = _resolve_netease_request_level(level)
    data = await netease.song_url_v1(song_id=id, cookie=cookie, level=requested_level)
    try:
        url = _resolve_netease_song_url(data)
        return {
            "url": url,
            "trial": False,
            "requested_level": _normalize_netease_quality_level(level, strict=True),
            "level": _resolve_netease_song_url_level(data),
            "br": _resolve_netease_song_url_br(data),
        }
    except HTTPException as e:
        if e.status_code == 402:
            trial_data = await netease.song_url(song_id=id, cookie=cookie, br=128000)
            url = _resolve_netease_song_url(trial_data)
            return {
                "url": url,
                "trial": True,
                "requested_level": _normalize_netease_quality_level(level, strict=True),
                "level": _resolve_netease_song_url_level(trial_data),
                "br": _resolve_netease_song_url_br(trial_data),
            }
        raise



def _get_netease_cookie_from_header(request: Request) -> str:
    c = (request.headers.get("x-netease-cookie") or "").strip()
    if not c:
        raise HTTPException(status_code=400, detail="netease cookie not set")
    if c.lower().startswith("cookie:"):
        c = c.split(":", 1)[1].strip()
    c = c.replace("\r", "").replace("\n", "")

    parts: list[str] = []
    banned = {"max-age", "expires", "path", "domain", "samesite"}
    for raw in c.split(";"):
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        if low in ("secure", "httponly"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k or not v:
            continue
        if k.lower() in banned:
            continue
        parts.append(f"{k}={v}")

    return "; ".join(parts) if parts else c


def _get_admin_cookie(session: Session) -> str:
    row = session.get(Secret, "netease_cookie")
    if not row:
        raise HTTPException(status_code=400, detail="admin netease cookie not set")
    try:
        cookie = decrypt_text(row.value).strip()
    except Exception:
        raise HTTPException(status_code=500, detail="failed to decrypt admin netease cookie")
    if not has_netease_auth_cookie(cookie):
        raise HTTPException(status_code=400, detail="admin netease cookie not set")
    return cookie


def _get_admin_qqmusic_cookie(session: Session) -> str:
    row = session.get(Secret, "qqmusic_cookie")
    if not row:
        raise HTTPException(status_code=400, detail="admin qqmusic cookie not set")
    try:
        return decrypt_text(row.value)
    except Exception:
        raise HTTPException(status_code=500, detail="failed to decrypt admin qqmusic cookie")


def _get_admin_bilibili_cookie(session: Session) -> str:
    row = session.get(Secret, "bilibili_cookie")
    if not row:
        raise HTTPException(status_code=400, detail="admin bilibili cookie not set")
    try:
        return decrypt_text(row.value)
    except Exception:
        raise HTTPException(status_code=500, detail="failed to decrypt admin bilibili cookie")


def _require_admin_token(request: Request) -> None:
    token = (settings.admin_token or "").strip()
    if not token:
        return
    provided = (request.headers.get("x-admin-token") or "").strip()
    if not provided:
        raise HTTPException(status_code=403, detail="missing admin token")
    if provided != token:
        raise HTTPException(status_code=403, detail="invalid admin token")


def _format_help() -> str:
    return (
        "Commands (no prefix):\n"
        "帮助|help - show this help\n"
        "状态|now - show now playing\n"
        "搜索|search <keywords> - search songs\n"
        "增加|add <song_id|keywords> - add to queue\n"
        "播放|play <song_id|keywords> - play now\n"
        "队列|queue - show queue\n"
        "暂停|pause / 恢复|resume / 停止|stop / 跳过|skip\n"
        "音量|vol <0-200> - set volume\n"
        "音效|fx - show audio fx\n"
        "fx pan <-1..1> / fx width <0..3> / fx swap <on|off> / fx bass <0..18> / fx reverb <0..1> / fx reset\n"
        "随机|shuffle - toggle shuffle on/off\n"
        "歌单|playlist <关键词> - 搜索并播放歌单\n"
        "选择|select <1-5> - 选择歌单"
    )


def _try_parse_song_id(s: str) -> str | None:
    t = (s or "").strip()
    if t.isdigit():
        return t
    return None


def _extract_song_meta_from_search_first(raw: dict) -> tuple[str, str, str] | None:
    songs = (((raw or {}).get("result") or {}).get("songs") or [])
    if not songs or not isinstance(songs, list):
        return None
    s0 = songs[0] or {}
    sid = str(s0.get("id") or "")
    if not sid:
        return None
    title = str(s0.get("name") or "")
    artist = ", ".join([str(a.get("name") or "") for a in (s0.get("ar") or []) if isinstance(a, dict)])
    return sid, title, artist


def _extract_song_meta_from_detail(detail: dict, song_id: str) -> tuple[str, str] | None:
    songs = (detail or {}).get("songs") or []
    if not songs or not isinstance(songs, list):
        return None
    s0 = songs[0] or {}
    title = str(s0.get("name") or song_id)
    artist = ", ".join([str(a.get("name") or "") for a in (s0.get("ar") or []) if isinstance(a, dict)])
    return title, artist


async def _enqueue_netease_song(
    *,
    song_id: str,
    title: str,
    artist: str,
    play_now: bool,
    requested_by: str,
    album: str = "",
    duration_ms: int | None = None,
    artwork_url: str = "",
    quality_level: str = "auto",
) -> tuple[int, bool]:
    session = new_session()
    try:
        normalized_level = _normalize_netease_quality_level(quality_level, strict=True)
        if not play_now:
            item = QueueItem(
                track_id=f"netease:{song_id}",
                title=title,
                artist=artist,
                album=album,
                duration=duration_ms,
                cover_url=artwork_url,
                source_url=_encode_netease_queue_meta(normalized_level),
            )
            session.add(item)
            session.commit()
            _schedule_ts_description_update()
            return int(item.id), False

        cookie = _get_admin_cookie(session)
        url, trial, notice, resolved_duration_ms, resolved_artist, resolved_album, resolved_artwork_url = await _resolve_netease_playback_payload(
            song_id=song_id,
            cookie=cookie,
            artist=artist,
            album=album,
            artwork_url=artwork_url,
            duration_ms=duration_ms,
            quality_level=normalized_level,
        )

        final_artist = resolved_artist or artist

        item = QueueItem(
            track_id=f"netease:{song_id}",
            title=title,
            artist=final_artist,
            album=resolved_album,
            duration=resolved_duration_ms,
            cover_url=resolved_artwork_url,
            source_url=_encode_netease_queue_source(normalized_level, url),
        )
        session.add(item)
        session.commit()

        _schedule_ts_description_update()

        await _set_now_playing_queue_item(
            int(item.id),
            url,
            duration_ms=resolved_duration_ms,
            artist=final_artist,
            album=resolved_album,
            artwork_url=resolved_artwork_url,
        )
        await voice.play(source_url=url, title=title, requested_by=requested_by, notice=notice)
        hist = HistoryItem(
            track_id=item.track_id,
            title=title,
            artist=final_artist,
            album=resolved_album,
            duration=resolved_duration_ms,
            cover_url=resolved_artwork_url,
            source_url=url,
            requested_by=requested_by,
        )
        session.add(hist)
        session.commit()

        return int(item.id), trial
    finally:
        session.close()


async def _enqueue_qqmusic_song(
    *,
    song_mid: str,
    title: str,
    artist: str,
    play_now: bool,
    requested_by: str,
    quality: str = "320",
    album_mid: str = "",
    duration_ms: int | None = None,
) -> tuple[int, bool]:
    """Enqueue a QQ Music song"""
    session = new_session()
    try:
        # Use admin QQ Music cookie (server-side), like netease.
        cookie = _get_admin_qqmusic_cookie(session)
        qqmusic.set_cookie(cookie)

        # Get music URL from QQ Music
        url = await qqmusic.get_music_url_simple(song_mid, quality)
        if not url:
            raise HTTPException(status_code=404, detail="无法获取 QQ 音乐播放链接，可能需要 VIP 会员或该歌曲不可用")
        
        # Get song cover using album MID
        album_cover_url = qqmusic.get_song_cover_image(album_mid) if album_mid else ""
        resolved_duration_ms = int(duration_ms) if duration_ms is not None and int(duration_ms) > 0 else 0
        
        # Create queue item
        item = QueueItem(
            track_id=f"qqmusic:{song_mid}",
            title=title,
            artist=artist,
            album="",  # QQ Music doesn't provide album info in basic API
            duration=resolved_duration_ms,
            cover_url=album_cover_url,
            source_url=url,
        )
        session.add(item)
        session.commit()

        _schedule_ts_description_update()

        if play_now:
            await _set_now_playing_queue_item(
                int(item.id),
                url,
                duration_ms=resolved_duration_ms,
                artist=artist,
                album="",
                artwork_url=album_cover_url,
            )
            await voice.play(source_url=url, title=title, requested_by=requested_by, notice="")
            hist = HistoryItem(
                track_id=item.track_id,
                title=title,
                artist=artist,
                album="",
                duration=resolved_duration_ms,
                cover_url=album_cover_url,
                source_url=url,
                requested_by=requested_by,
            )
            session.add(hist)
            session.commit()

        return int(item.id), False  # QQ Music doesn't have trial mode
    finally:
        session.close()


async def _enqueue_bilibili_song(
    *,
    video_id: str,
    title: str,
    artist: str,
    play_now: bool,
    requested_by: str,
    album: str = "",
    duration_ms: int | None = None,
    artwork_url: str = "",
) -> tuple[int, bool]:
    session = new_session()
    play_request_generation: int | None = None
    try:
        normalized_video_id = _extract_bilibili_video_id(video_id)
        if not normalized_video_id:
            raise HTTPException(status_code=400, detail="video_id is empty")

        _ensure_bilibili_duration_allowed(duration_ms, video_id=normalized_video_id, title=title)

        if not play_now:
            item = QueueItem(
                track_id=f"bilibili:{normalized_video_id}",
                title=title,
                artist=artist,
                album=album,
                duration=duration_ms,
                cover_url=artwork_url,
                source_url="",
            )
            session.add(item)
            session.commit()
            _schedule_ts_description_update()
            return int(item.id), False

        play_request_generation = await _begin_play_request()
        duration_ms, artist, album, artwork_url = await _hydrate_bilibili_track_metadata(
            video_id=normalized_video_id,
            title=title,
            artist=artist,
            album=album,
            artwork_url=artwork_url,
            duration_ms=duration_ms,
        )

        if not await _is_play_request_current(play_request_generation):
            raise HTTPException(status_code=409, detail="bilibili playback request was superseded by a newer command")

        source_url, resolved_duration_ms, resolved_artist, resolved_album, resolved_artwork_url = await _resolve_bilibili_playback_payload(
            video_id=normalized_video_id,
            artist=artist,
            album=album,
            artwork_url=artwork_url,
            duration_ms=duration_ms,
        )

        if not await _is_play_request_current(play_request_generation):
            raise HTTPException(status_code=409, detail="bilibili playback request was superseded by a newer command")

        final_artist = resolved_artist or artist

        item = QueueItem(
            track_id=f"bilibili:{normalized_video_id}",
            title=title,
            artist=final_artist,
            album=resolved_album,
            duration=resolved_duration_ms,
            cover_url=resolved_artwork_url,
            source_url=source_url,
        )
        session.add(item)
        session.commit()

        _schedule_ts_description_update()

        await _set_now_playing_queue_item(
            int(item.id),
            source_url,
            duration_ms=resolved_duration_ms,
            artist=final_artist,
            album=resolved_album,
            artwork_url=resolved_artwork_url,
        )

        if not await _is_play_request_current(play_request_generation):
            await _take_now_playing_if_match(source_url=source_url)
            raise HTTPException(status_code=409, detail="bilibili playback request was superseded by a newer command")

        await voice.play(source_url=source_url, title=title, requested_by=requested_by, notice="")

        if not await _is_play_request_current(play_request_generation):
            raise HTTPException(status_code=409, detail="bilibili playback request was superseded by a newer command")

        hist = HistoryItem(
            track_id=item.track_id,
            title=title,
            artist=final_artist,
            album=resolved_album,
            duration=resolved_duration_ms,
            cover_url=resolved_artwork_url,
            source_url=source_url,
            requested_by=requested_by,
        )
        session.add(hist)
        session.commit()

        return int(item.id), False
    finally:
        session.close()


async def _handle_chat_command(invoker_name: str, message: str, *, target_mode: int = 2) -> None:
    raw = (message or "")
    msg = raw.strip()
    if not msg:
        return

    s = msg
    if s.startswith("!") or s.startswith("！"):
        s = s[1:].lstrip()
    if not s:
        return

    head = s
    tail = ""
    for sep in (" ", "\t", ":", "："):
        idx = s.find(sep)
        if idx != -1:
            head = s[:idx]
            tail = s[idx + 1 :]
            if sep in (":", "："):
                tail = tail.lstrip()
            break

    head_norm = head.strip().lower()
    alias_to_cmd = {
        "help": "help",
        "h": "help",
        "?": "help",
        "帮助": "help",
        "菜单": "help",
        "指令": "help",
        "命令": "help",
        "search": "search",
        "s": "search",
        "find": "search",
        "搜": "search",
        "搜索": "search",
        "查": "search",
        "add": "add",
        "a": "add",
        "加": "add",
        "增加": "add",
        "入队": "add",
        "点歌": "add",
        "play": "play",
        "p": "play",
        "播放": "play",
        "来一首": "play",
        "放": "play",
        "vol": "vol",
        "volume": "vol",
        "音量": "vol",
        "声音": "vol",
        "now": "now",
        "np": "now",
        "status": "now",
        "状态": "now",
        "当前": "now",
        "queue": "queue",
        "q": "queue",
        "队列": "queue",
        "列表": "queue",
        "pause": "pause",
        "暂停": "pause",
        "resume": "resume",
        "continue": "resume",
        "恢复": "resume",
        "继续": "resume",
        "stop": "stop",
        "停止": "stop",
        "skip": "skip",
        "next": "skip",
        "跳过": "skip",
        "下一首": "skip",
        "切歌": "skip",
        "desc": "desc",
        "简介": "desc",
        "签名": "desc",
        "fx": "fx",
        "音效": "fx",
        "shuffle": "shuffle",
        "随机": "shuffle",
        "歌单": "playlist",
        "playlist": "playlist",
        "select": "select",
        "选择": "select",
    }

    cmd = alias_to_cmd.get(head_norm)
    if not cmd:
        return
    arg = tail.strip()

    # Declare globals for state variables used across handlers
    global _pending_playlist_select, _pending_playlist_keywords

    async def reply(text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        if len(t) > 700:
            t = t[:700] + "..."
        await voice.send_notice(t, target_mode=int(target_mode))

    try:
        if cmd in ("help", "h"):
            await reply(_format_help())
            return

        if cmd in ("now", "np", "status"):
            st = await voice.get_status()
            session = new_session()
            try:
                q_total = int(session.execute(select(func.count(QueueItem.id))).scalar() or 0)
            finally:
                session.close()
            title = (st.now_playing_title or "").strip()
            if title:
                await reply(f"当前: {title}\n状态: {st.state} / 音量: {st.volume_percent} / 队列: {q_total}")
            else:
                await reply(f"当前: (空闲)\n状态: {st.state} / 音量: {st.volume_percent} / 队列: {q_total}")
            return

        if cmd == "queue":
            session = new_session()
            try:
                total = int(session.execute(select(func.count(QueueItem.id))).scalar() or 0)
                rows = session.execute(select(QueueItem).order_by(QueueItem.id.asc()).limit(5)).scalars().all()
                if not rows:
                    await reply("队列为空")
                    return
                lines = [f"#{r.id} {r.title} - {r.artist}".strip(" -") for r in rows]
                await reply(f"队列(前{len(lines)}/共{total}):\n" + "\n".join(lines))
                return
            finally:
                session.close()

        if cmd == "pause":
            await _mark_playback_paused()
            await voice.pause()
            await reply("已暂停")
            return

        if cmd in ("resume", "continue"):
            st = await voice.get_status()
            cur = str(st.state or "").strip().upper()
            if cur != "STATE_PAUSED":
                await reply("当前没有暂停的歌曲")
                return
            await _mark_playback_resumed()
            await voice.resume()
            await reply("已恢复")
            return

        if cmd == "stop":
            await _invalidate_play_requests()
            await _set_now_playing_queue_item(None)
            await voice.stop()
            await reply("已停止")
            return

        if cmd == "skip":
            # Get current playing item to remove it
            current_item_id = None
            pending_item_id = None
            async with _playback_lock:
                current_item_id = _current_queue_item_id
                pending_item_id = _pending_queue_item_id
            active_item_id = current_item_id or pending_item_id

            # Also check real voice-service state
            st = await voice.get_status()
            cur = str(st.state or "").strip().upper()
            is_playing_or_paused = cur in ("STATE_PLAYING", "STATE_PAUSED")

            if active_item_id:
                # Remove current song from queue
                await _remove_queue_item_internal(active_item_id)
                await _invalidate_play_requests()

                # Stop current playback if voice-service knows about it
                await _set_now_playing_queue_item(None)
                if is_playing_or_paused:
                    await voice.skip()
                    # voice-service auto-advances; STARTED event will sync backend state
                else:
                    # Nothing playing in voice-service — just auto-play from queue
                    await _auto_play_next_from_queue(start_after_id=active_item_id)
                await reply("已跳过当前歌曲并播放下一首")
            else:
                # Nothing tracked in backend, but voice-service might still be playing
                if is_playing_or_paused:
                    await voice.skip()
                    await reply("已跳过")
                else:
                    # Queue might have items even if nothing is tracked — try auto-play
                    await _auto_play_next_from_queue()
                    await reply("已跳过（状态已同步）")
            return

        if cmd in ("vol", "volume"):
            if not arg:
                await reply("用法: vol <0-200>")
                return
            try:
                v = int(arg)
            except ValueError:
                await reply("用法: vol <0-200>")
                return
            v = max(0, min(200, v))
            await voice.set_volume(v)
            session = new_session()
            try:
                row = session.get(Secret, "voice_volume")
                if not row:
                    row = Secret(key="voice_volume", value=str(v))
                    session.add(row)
                else:
                    row.value = str(v)
                session.commit()
            finally:
                session.close()
            await reply(f"音量已设置为 {v}")
            return

        if cmd == "fx":
            if not arg:
                fx = await voice.get_audio_fx()
                await reply(
                    f"音效: pan={fx.pan:.2f} width={fx.width:.2f} swap_lr={int(fx.swap_lr)} bass_db={fx.bass_db:.1f} reverb_mix={fx.reverb_mix:.2f}\n"
                    "用法: fx pan <-1..1> | fx width <0..3> | fx swap <on|off> | fx bass <0..18> | fx reverb <0..1> | fx reset"
                )
                return

            parts = [p for p in arg.split() if p]
            sub = (parts[0] if parts else "").strip().lower()

            if sub == "reset":
                await voice.set_audio_fx(pan=0.0, width=1.0, swap_lr=False, bass_db=0.0, reverb_mix=0.0)
                fx = await voice.get_audio_fx()
                await reply(
                    f"已重置音效: pan={fx.pan:.2f} width={fx.width:.2f} swap_lr={int(fx.swap_lr)} bass_db={fx.bass_db:.1f} reverb_mix={fx.reverb_mix:.2f}"
                )
                return

            if len(parts) < 2:
                await reply("用法: fx pan <-1..1> | fx width <0..3> | fx swap <on|off> | fx bass <0..18> | fx reverb <0..1> | fx reset")
                return

            val = parts[1].strip().lower()
            if sub == "pan":
                try:
                    p = float(val)
                except ValueError:
                    await reply("用法: fx pan <-1..1>")
                    return
                await voice.set_audio_fx(pan=max(-1.0, min(1.0, p)))
            elif sub == "width":
                try:
                    w = float(val)
                except ValueError:
                    await reply("用法: fx width <0..3>")
                    return
                await voice.set_audio_fx(width=max(0.0, min(3.0, w)))
            elif sub == "swap":
                on = val in ("1", "true", "on", "yes", "y", "开")
                off = val in ("0", "false", "off", "no", "n", "关")
                if not (on or off):
                    await reply("用法: fx swap <on|off>")
                    return
                await voice.set_audio_fx(swap_lr=bool(on))
            elif sub == "bass":
                try:
                    b = float(val)
                except ValueError:
                    await reply("用法: fx bass <0..18>")
                    return
                await voice.set_audio_fx(bass_db=max(0.0, min(18.0, b)))
            elif sub == "reverb":
                try:
                    m = float(val)
                except ValueError:
                    await reply("用法: fx reverb <0..1>")
                    return
                await voice.set_audio_fx(reverb_mix=max(0.0, min(1.0, m)))
            else:
                await reply("用法: fx pan <-1..1> | fx width <0..3> | fx swap <on|off> | fx bass <0..18> | fx reverb <0..1> | fx reset")
                return

            fx = await voice.get_audio_fx()
            await reply(
                f"音效已更新: pan={fx.pan:.2f} width={fx.width:.2f} swap_lr={int(fx.swap_lr)} bass_db={fx.bass_db:.1f} reverb_mix={fx.reverb_mix:.2f}"
            )
            return

        if cmd == "desc":
            if not arg:
                await reply("用法: desc <内容>")
                return
            await voice.set_client_description(arg)
            await reply("简介已更新")
            return

        if cmd == "playlist":
            global _pending_playlist_select, _pending_playlist_keywords
            if not arg:
                await reply("用法: 歌单 <关键词>")
                return
            keywords = arg.strip()
            raw = await netease.search(keywords=keywords, limit=5, type_=1000)
            playlists = (((raw or {}).get("result") or {}).get("playlists") or [])
            if not playlists:
                await reply("没有找到歌单")
                return
            _pending_playlist_select = [
                {"id": str(p.get("id") or ""), "name": str(p.get("name") or ""), "creator": str((p.get("creator") or {}).get("nickname") or ""), "trackCount": int(p.get("trackNumberUpdateTime") or 0) or int(p.get("trackCount") or 0)}
                for p in playlists
                if p.get("id")
            ]
            _pending_playlist_keywords = keywords
            lines = [f"歌单搜索结果({len(_pending_playlist_select)}):"]
            for i, pl in enumerate(_pending_playlist_select, 1):
                lines.append(f"{i}. {pl['name']} - {pl['creator']} (共{pl['trackCount']}首)")
            await reply("\n".join(lines))
            return

        if cmd == "select":
            if not arg:
                await reply("用法: 选择 <1-5>")
                return
            try:
                idx = int(arg.strip()) - 1
            except ValueError:
                await reply("用法: 选择 <1-5>")
                return
            if _pending_playlist_select is None or idx < 0 or idx >= len(_pending_playlist_select):
                await reply("没有待选择的歌单，请先用 歌单 <关键词> 搜索")
                return
            pl = _pending_playlist_select[idx]
            _pending_playlist_select = None
            _pending_playlist_keywords = ""
            session = new_session()
            try:
                cookie = _get_admin_cookie(session)
            finally:
                session.close()
            raw = await netease.playlist_detail(playlist_id=pl["id"], cookie=cookie)
            tracks = (((raw or {}).get("playlist") or {}).get("tracks") or [])
            if not tracks:
                await reply("歌单为空")
                return
            # Enqueue all tracks (no play_now for first)
            added_ids: list[int] = []
            for i, t in enumerate(tracks):
                sid = str(t.get("id") or "")
                if not sid:
                    continue
                title = str(t.get("name") or sid)
                artist = ", ".join([str(a.get("name") or "") for a in (t.get("ar") or []) if isinstance(a, dict)])
                album = str((t.get("al") or {}).get("name") or "")
                duration_ms = int(t.get("dt") or 0)
                artwork_url = str((t.get("al") or {}).get("picUrl") or "")
                item_id, _ = await _enqueue_netease_song(
                    song_id=sid,
                    title=title,
                    artist=artist,
                    play_now=False,
                    requested_by=invoker_name,
                    album=album,
                    duration_ms=duration_ms,
                    artwork_url=artwork_url,
                )
                added_ids.append(item_id)
            _schedule_ts_description_update()
            if not added_ids:
                await reply("歌单中没有可播放的歌曲")
                return
            # Auto-play first track now
            st = await voice.get_status()
            cur = str(st.state or "").strip().upper()
            if cur == "STATE_IDLE":
                await _auto_play_next_from_queue()
                await reply(f"已加载歌单「{pl['name']}」共 {len(added_ids)} 首并开始播放")
            else:
                await reply(f"已加载歌单「{pl['name']}」共 {len(added_ids)} 首到队列")
            return

        if cmd == "shuffle":
            global _shuffle_enabled, _shuffle_queue, _current_shuffle_index
            import random as _random_module
            new_state = not _shuffle_enabled
            _shuffle_enabled = new_state
            if new_state:
                session = new_session()
                try:
                    queue_items = session.execute(select(QueueItem).order_by(QueueItem.id.asc())).scalars().all()
                    queue_ids = [item.id for item in queue_items]
                    _shuffle_queue = queue_ids.copy()
                    for i in range(len(_shuffle_queue) - 1, 0, -1):
                        j = _random_module.randint(0, i)
                        _shuffle_queue[i], _shuffle_queue[j] = _shuffle_queue[j], _shuffle_queue[i]
                    if _current_queue_item_id and _current_queue_item_id in _shuffle_queue:
                        _current_shuffle_index = _shuffle_queue.index(_current_queue_item_id)
                    else:
                        _current_shuffle_index = -1
                finally:
                    session.close()
                await reply(f"随机播放已开启 ({len(_shuffle_queue)} 首)")
            else:
                _shuffle_queue = []
                _current_shuffle_index = -1
                await reply("随机播放已关闭")
            return

        if cmd == "search":
            if not arg:
                await reply("用法: search <关键词>")
                return
            raw = await netease.search(keywords=arg, limit=5)
            songs = (((raw or {}).get("result") or {}).get("songs") or [])
            if not songs:
                await reply("没有找到结果")
                return

            # Enrich with song detail to get complete artist/album info.
            ids = [str((s or {}).get("id") or "").strip() for s in songs if isinstance(s, dict)]
            ids = [i for i in ids if i]
            by_id: dict[str, dict] = {}
            if ids:
                session = new_session()
                try:
                    cookie = _get_admin_cookie(session)
                finally:
                    session.close()
                detail = await netease.song_detail(song_id=",".join(ids), cookie=cookie)
                dsongs = (detail or {}).get("songs") or []
                for d in dsongs:
                    if isinstance(d, dict):
                        sid = str(d.get("id") or "").strip()
                        if sid:
                            by_id[sid] = d

            lines: list[str] = []
            for i, s in enumerate(songs[:5], start=1):
                sid = str((s or {}).get("id") or "")
                title = str((s or {}).get("name") or "")
                # Prefer detail's ar; fall back to search result's ar then artists.
                ar = None
                if sid and sid in by_id:
                    ar = by_id[sid].get("ar") or []
                if not ar:
                    ar = (s or {}).get("ar") or s.get("artists") or []
                artist = ", ".join([str(a.get("name") or "") for a in ar if isinstance(a, dict)])
                lines.append(f"{i}. {sid} {title} - {artist}".strip())
            await reply("搜索结果(可直接用 add/play + 歌曲ID):\n" + "\n".join(lines))
            return

        if cmd in ("add", "play"):
            if not arg:
                await reply(f"用法: {cmd} <歌曲ID|关键词>")
                return

            song_id = _try_parse_song_id(arg)
            title = ""
            artist = ""

            if song_id is None:
                raw = await netease.search(keywords=arg, limit=1)
                meta = _extract_song_meta_from_search_first(raw)
                if meta is None:
                    await reply("没有找到结果")
                    return
                song_id, title, artist = meta
            else:
                # Use admin cookie for detail lookup.
                session = new_session()
                try:
                    cookie = _get_admin_cookie(session)
                finally:
                    session.close()
                detail = await netease.song_detail(song_id=song_id, cookie=cookie)
                meta2 = _extract_song_meta_from_detail(detail, song_id)
                if meta2 is not None:
                    title, artist = meta2
                else:
                    title = song_id

            item_id, trial = await _enqueue_netease_song(
                song_id=song_id,
                title=title,
                artist=artist,
                play_now=(cmd == "play"),
                requested_by=invoker_name,
                quality_level="auto",
            )
            song_label = f"{title} - {artist}".strip(" -")
            extra = ""
            if trial:
                extra = "(试听)"
            if cmd == "play":
                await reply(f"立即播放: #{item_id} {song_label} {extra}\n点歌: {invoker_name}")
                return

            auto_started = False
            try:
                st = await voice.get_status()
                cur = str(getattr(st, "state", "") or "").strip().upper()
                if cur == "STATE_IDLE":
                    await _auto_play_next_from_queue()
                    auto_started = True
            except Exception as e:
                await reply(f"已加入队列: #{item_id} {song_label} {extra}\n点歌: {invoker_name}\n自动播放失败: {e}")
                return

            if auto_started:
                await reply(f"已加入队列并开始播放: #{item_id} {song_label} {extra}\n点歌: {invoker_name}")
            else:
                await reply(f"已加入队列: #{item_id} {song_label} {extra}\n点歌: {invoker_name}")

            return

        await reply("unknown command, try !help")
    except HTTPException as e:
        detail = str(getattr(e, "detail", "") or "").strip()
        if e.status_code == 404:
            await reply("加载失败：歌曲不存在/已下架（无版权或资源不可用）")
            return
        if e.status_code == 402:
            await reply("加载失败：需要 VIP/付费账号（已尝试试听/降码率，如仍失败请换歌）")
            return
        if e.status_code == 403:
            await reply("加载失败：无版权/地区限制/不可播放")
            return
        if detail:
            await reply(f"error: {e.status_code}: {detail}")
        else:
            await reply(f"error: {e.status_code}")
    except Exception as e:
        await reply(f"error: {e}")


async def _chat_command_worker() -> None:
    while True:
        try:
            async for ev in voice.subscribe_events(include_chat=True, include_playback=True, include_log=False):
                try:
                    if not hasattr(ev, "WhichOneof"):
                        continue
                    kind = ev.WhichOneof("payload")

                    if kind == "chat":
                        chat = ev.chat
                        try:
                            logger.info(
                                "ts3 chat event: target_mode=%s invoker=%s msg=%s",
                                int(getattr(chat, "target_mode", 0) or 0),
                                str(getattr(chat, "invoker_name", "") or ""),
                                str(getattr(chat, "message", "") or ""),
                            )
                        except Exception:
                            pass
                        await _handle_chat_command(
                            str(getattr(chat, "invoker_name", "")),
                            str(getattr(chat, "message", "")),
                            target_mode=int(getattr(chat, "target_mode", 2) or 2),
                        )
                        continue

                    if kind == "playback":
                        pb = ev.playback
                        ty = int(getattr(pb, "type", 0) or 0)
                        src = str(getattr(pb, "source_url", "") or "")
                        # PlaybackEvent.Type: STARTED=1, FINISHED=2, ERROR=3
                        if ty == 1:
                            # Sync backend state: find the queue item matching this source_url
                            session = new_session()
                            try:
                                row = session.execute(
                                    select(QueueItem).where(QueueItem.source_url == src).limit(1)
                                ).scalars().first()
                                if row is not None:
                                    await _set_now_playing_queue_item(
                                        int(row.id),
                                        src,
                                        duration_ms=row.duration,
                                        artist=row.artist or "",
                                        album=row.album or "",
                                        artwork_url=row.cover_url or "",
                                    )
                            finally:
                                session.close()
                            continue
                        if ty == 2:
                            item_id = await _take_now_playing_if_match(source_url=src)
                            if item_id is not None:
                                await _delete_queue_item(item_id)
                                await _auto_play_next_from_queue()
                        if ty == 3:
                            item_id = await _take_now_playing_if_match(source_url=src)
                            if item_id is not None:
                                await _delete_queue_item(item_id)
                                try:
                                    await voice.send_notice(
                                        f"播放失败，已跳过并删除: #{item_id}\n将播放下一首",
                                        target_mode=2,
                                    )
                                except Exception:
                                    pass
                                await _auto_play_next_from_queue()
                        continue
                except Exception:
                    logger.exception("chat worker: failed to handle event")
                    continue
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("chat worker: subscribe loop crashed; retrying")
            await asyncio.sleep(2)


def _set_secret(session: Session, key: str, plaintext: str) -> None:
    row = session.get(Secret, key)
    enc = encrypt_text(plaintext)
    if not row:
        row = Secret(key=key, value=enc)
        session.add(row)
    else:
        row.value = enc
    session.commit()


@app.get("/admin/status")
def admin_status(session: Session = Depends(get_session)) -> dict:
    row = session.get(Secret, "netease_cookie")
    if not row or not row.value:
        return {"admin_cookie_set": False}
    try:
        cookie = decrypt_text(row.value).strip()
    except Exception:
        cookie = ""
    return {"admin_cookie_set": has_netease_auth_cookie(cookie)}


@app.get("/admin/account")
async def admin_account(request: Request, session: Session = Depends(get_session)) -> dict:
    _require_admin_token(request)
    cookie = _get_admin_cookie(session)
    data = await netease.user_account(cookie=cookie)
    profile = (data or {}).get("profile") or {}
    account = (data or {}).get("account") or {}
    return {
        "user_id": profile.get("userId") or account.get("id"),
        "nickname": profile.get("nickname") or "",
        "vip_type": profile.get("vipType"),
    }


@app.post("/admin/ts/description")
async def admin_ts_description(req: TSClientDescriptionRequest, request: Request) -> dict:
    _require_admin_token(request)
    desc = (req.description or "").strip()
    if len(desc) > 700:
        raise HTTPException(status_code=400, detail="description too long")
    await voice.set_client_description(desc)
    return {"ok": True}


@app.get("/admin/debug/cookie")
async def admin_debug_cookie(request: Request, session: Session = Depends(get_session)) -> dict:
    _require_admin_token(request)
    cookie = _get_admin_cookie(session)
    return {"fingerprint": _cookie_fingerprint(cookie)}


@app.get("/admin/debug/config")
async def admin_debug_config(request: Request) -> dict:
    _require_admin_token(request)
    return {
        "cookie_key_fingerprint": _cookie_key_fingerprint(),
        "netease_api_base": settings.netease_api_base,
    }


@app.get("/admin/debug/runtime")
async def admin_debug_runtime(request: Request) -> dict:
    _require_admin_token(request)
    sqlite_db_path = get_sqlite_db_path()
    return {
        "cwd": os.getcwd(),
        "sqlite_db_path": str(Path(sqlite_db_path).resolve()) if sqlite_db_path else None,
        "database_url": get_database_url(),
    }


@app.get("/admin/debug/song_url")
async def admin_debug_song_url(request: Request, id: str, level: str = "auto", session: Session = Depends(get_session)) -> dict:
    _require_admin_token(request)
    cookie = _get_admin_cookie(session)

    detail = await netease.song_detail(song_id=id, cookie=cookie)
    dt = _resolve_netease_duration_ms(detail)

    requested_level = _normalize_netease_quality_level(level, strict=True)
    data = await netease.song_url_v1(song_id=id, cookie=cookie, level=_resolve_netease_request_level(requested_level))
    trial = False
    try:
        url = _resolve_netease_song_url(data)
    except HTTPException as e:
        if e.status_code == 402:
            trial_data = await netease.song_url(song_id=id, cookie=cookie, br=128000)
            url = _resolve_netease_song_url(trial_data)
            trial = True
        else:
            raise

    it = _extract_netease_song_url_item(data)

    return {
        "song_id": id,
        "trial": trial,
        "duration_ms": dt,
        "url": url,
        "requested_level": requested_level,
        "song_url_item": {
            "code": it.get("code"),
            "fee": it.get("fee"),
            "payed": it.get("payed"),
            "level": it.get("level"),
            "br": it.get("br"),
        },
        "cookie_fingerprint": _cookie_fingerprint(cookie),
    }


@app.post("/admin/cookie")
def admin_set_cookie(
    req: AdminCookieSetRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    _require_admin_token(request)
    c = (req.cookie or "").strip()
    if not c:
        raise HTTPException(status_code=400, detail="cookie is empty")
    if c.lower().startswith("cookie:"):
        c = c.split(":", 1)[1].strip()
    c = c.replace("\r", "").replace("\n", "")
    if not has_netease_auth_cookie(c):
        raise HTTPException(status_code=400, detail="cookie does not contain a usable netease auth token")
    _set_secret(session, "netease_cookie", c)
    return {"ok": True, "admin_cookie_set": True}


@app.get("/admin/qr/key")
async def admin_qr_key(request: Request) -> dict:
    _require_admin_token(request)
    return await netease.qr_key()


@app.get("/admin/qr/create")
async def admin_qr_create(key: str, request: Request) -> dict:
    _require_admin_token(request)
    return await netease.qr_create(key)


@app.get("/admin/qr/check")
async def admin_qr_check(key: str, request: Request, session: Session = Depends(get_session)) -> dict:
    _require_admin_token(request)
    data = await netease.qr_check(key)
    code = (data or {}).get("code")
    if code == 803:
        cookie = extract_netease_auth_cookie(str((data or {}).get("cookie") or ""))
        if not cookie:
            return {
                "code": code,
                "message": "authorized but no usable authentication cookie was returned",
                "admin_cookie_set": False,
            }
        _set_secret(session, "netease_cookie", cookie)
        return {"code": code, "message": "authorized", "admin_cookie_set": True}
    if code == 800:
        return {"code": code, "message": "expired", "admin_cookie_set": False}
    if code == 802:
        return {"code": code, "message": "scanned", "admin_cookie_set": False}
    if code == 801:
        return {"code": code, "message": "waiting", "admin_cookie_set": False}
    return {"code": code, "message": "unknown", "admin_cookie_set": False, "raw": data}


@app.get("/netease/account")
async def netease_account(request: Request) -> dict:
    cookie = _get_netease_cookie_from_header(request)
    return await netease.user_account(cookie=cookie)


@app.get("/netease/likelist")
async def netease_likelist(request: Request, offset: int = 0, limit: int = 0) -> dict:
    cookie = _get_netease_cookie_from_header(request)
    account = await netease.user_account(cookie=cookie)
    profile = (account or {}).get("profile") or {}
    uid = profile.get("userId")
    if not uid:
        raise HTTPException(status_code=400, detail="unable to determine uid from cookie")
    data = await netease.likelist(uid=str(uid), cookie=cookie)
    ids = (data or {}).get("ids") or []

    songs: list[dict] = []
    try:
        if isinstance(ids, list) and ids:
            chunk_size = 200
            id_strs = [str(i) for i in ids if i is not None and str(i).strip()]

            if offset < 0:
                offset = 0
            if limit and limit > 0:
                page_ids = id_strs[offset : offset + limit]
            else:
                page_ids = id_strs

            async def _fetch_song_detail(chunk: list[str]) -> list[dict]:
                if not chunk:
                    return []
                detail = await netease.song_detail(song_id=",".join(chunk), cookie=cookie)
                dsongs = (detail or {}).get("songs") or []
                if isinstance(dsongs, list) and dsongs:
                    return [s for s in dsongs if isinstance(s, dict)]
                return []

            chunks = [page_ids[i : i + chunk_size] for i in range(0, len(page_ids), chunk_size)]
            results = await asyncio.gather(*[_fetch_song_detail(c) for c in chunks], return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    continue
                songs.extend(r)
    except Exception:
        songs = []

    # Keep original fields (ids, code, etc.) and add songs for frontend rendering.
    out = dict(data or {})
    out["songs"] = songs
    try:
        if isinstance(ids, list):
            out["total"] = len(ids)
            out["offset"] = int(offset)
            out["limit"] = int(limit)
            if limit and limit > 0:
                out["has_more"] = (offset + limit) < len(ids)
    except Exception:
        pass
    return out


@app.get("/netease/likes")
async def netease_likes(request: Request, offset: int = 0, limit: int = 0) -> dict:
    """Alias for likelist to match frontend expectations"""
    return await netease_likelist(request, offset=offset, limit=limit)


@app.get("/netease/playlists")
async def netease_playlists(request: Request) -> dict:
    cookie = _get_netease_cookie_from_header(request)
    account = await netease.user_account(cookie=cookie)
    profile = (account or {}).get("profile") or {}
    uid = profile.get("userId")
    if not uid:
        raise HTTPException(status_code=400, detail="unable to determine uid from cookie")
    return await netease.user_playlist(uid=str(uid), cookie=cookie)


@app.post("/queue/netease")
async def add_queue_netease(req: AddNeteaseQueueRequest) -> dict:
    try:
        item_id, trial = await _enqueue_netease_song(
            song_id=req.song_id,
            title=req.title,
            artist=req.artist,
            play_now=req.play_now,
            requested_by="web",
            album=req.album,
            duration_ms=req.duration_ms,
            artwork_url=req.cover_url,
            quality_level=req.level,
        )
        return {"ok": True, "id": item_id, "trial": trial}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enqueue netease song {req.song_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/queue/qqmusic")
async def add_queue_qqmusic(req: AddQQMusicQueueRequest) -> dict:
    try:
        item_id, trial = await _enqueue_qqmusic_song(
            song_mid=req.song_mid,
            title=req.title,
            artist=req.artist,
            play_now=req.play_now,
            requested_by="web",
            quality=req.quality,
            album_mid=req.album_mid,
            duration_ms=req.duration_ms,
        )
        return {"ok": True, "id": item_id, "trial": trial}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enqueue qqmusic song {req.song_mid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/queue/bilibili")
async def add_queue_bilibili(req: AddBilibiliQueueRequest) -> dict:
    try:
        item_id, trial = await _enqueue_bilibili_song(
            video_id=req.video_id,
            title=req.title,
            artist=req.artist,
            play_now=req.play_now,
            requested_by="web",
            album=req.album,
            duration_ms=req.duration_ms,
            artwork_url=req.cover_url,
        )
        return {"ok": True, "id": item_id, "trial": trial}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enqueue bilibili video {req.video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/queue")
def get_queue(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(select(QueueItem).order_by(QueueItem.id.asc())).scalars().all()
    return [_serialize_queue_item(row) for row in rows]


@app.delete("/queue")
async def clear_queue(session: Session = Depends(get_session)) -> dict:
    global _shuffle_queue, _current_shuffle_index

    removed_count = int(session.execute(select(func.count(QueueItem.id))).scalar() or 0)
    session.execute(delete(QueueItem))
    session.commit()

    _shuffle_queue = []
    _current_shuffle_index = -1

    await _set_now_playing_queue_item(None)
    await _invalidate_play_requests()

    playback_stopped = False
    try:
        await voice.stop()
        playback_stopped = True
    except Exception:
        playback_stopped = False

    _schedule_ts_description_update()
    return {"ok": True, "removed_count": removed_count, "playback_stopped": playback_stopped}


@app.post("/queue")
def add_queue(req: AddQueueRequest, session: Session = Depends(get_session)) -> dict:
    item = QueueItem(
        track_id=req.track_id,
        title=req.title,
        artist=req.artist,
        source_url=req.source_url,
    )
    session.add(item)
    session.commit()
    return {"ok": True, "id": item.id}


@app.delete("/queue/{item_id}")
def delete_queue_item(item_id: int, session: Session = Depends(get_session)) -> dict:
    item = session.get(QueueItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    session.delete(item)
    session.commit()

    _schedule_ts_description_update()
    return {"ok": True}


@app.post("/queue/{item_id}/play")
async def play_queue_item(item_id: int, session: Session = Depends(get_session)) -> dict:
    ok = await _play_queue_item_internal(item_id, requested_by="web")
    if not ok:
        raise HTTPException(status_code=404, detail="queue item not found")

    _schedule_ts_description_update()
    return {"ok": True}


@app.get("/history")
def history(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(select(HistoryItem).order_by(HistoryItem.id.desc()).limit(200)).scalars().all()
    return [_serialize_history_item(row) for row in rows]


async def _replay_history_item(
    hist_item: HistoryItem,
    *,
    play_now: bool,
    requested_by: str,
) -> dict:
    track_id = str(hist_item.track_id or "").strip()
    if not track_id:
        raise HTTPException(status_code=400, detail="history track_id is empty")

    if track_id.startswith("netease:"):
        song_id = track_id.split(":", 1)[1].strip()
        if not song_id:
            raise HTTPException(status_code=400, detail="netease song_id is empty")

        item_id, trial = await _enqueue_netease_song(
            song_id=song_id,
            title=hist_item.title,
            artist=hist_item.artist,
            play_now=play_now,
            requested_by=requested_by,
            album=hist_item.album,
            duration_ms=hist_item.duration,
            artwork_url=hist_item.cover_url,
        )
        return {
            "ok": True,
            "source": "netease",
            "queue_id": item_id,
            "trial": trial,
            "play_now": play_now,
            "message": f"{'Playing' if play_now else 'Added to queue'}: {hist_item.title}",
            "track": {
                "source": "netease",
                "track_id": f"netease:{song_id}",
                "song_id": song_id,
            },
        }

    if track_id.startswith("bilibili:"):
        video_id = _extract_bilibili_video_id(track_id)
        if not video_id:
            raise HTTPException(status_code=400, detail="bilibili video_id is empty")

        item_id, trial = await _enqueue_bilibili_song(
            video_id=video_id,
            title=hist_item.title,
            artist=str(hist_item.artist or ""),
            play_now=play_now,
            requested_by=requested_by,
            album=str(hist_item.album or ""),
            duration_ms=hist_item.duration,
            artwork_url=str(hist_item.cover_url or ""),
        )
        return {
            "ok": True,
            "source": "bilibili",
            "queue_id": item_id,
            "trial": trial,
            "play_now": play_now,
            "message": f"{'Playing' if play_now else 'Added to queue'}: {hist_item.title}",
            "track": {
                "source": "bilibili",
                "track_id": f"bilibili:{video_id}",
                "video_id": video_id,
                "webpage_url": _build_bilibili_video_url(video_id),
            },
        }

    if track_id.startswith("qqmusic:"):
        song_mid = track_id.split(":", 1)[1].strip()
        if not song_mid:
            raise HTTPException(status_code=400, detail="qqmusic song_mid is empty")

        item_id, trial = await _enqueue_qqmusic_song(
            song_mid=song_mid,
            title=hist_item.title,
            artist=str(hist_item.artist or ""),
            play_now=play_now,
            requested_by=requested_by,
            quality="320",
            album_mid="",
            duration_ms=hist_item.duration,
        )
        return {
            "ok": True,
            "source": "qqmusic",
            "queue_id": item_id,
            "trial": trial,
            "play_now": play_now,
            "message": f"{'Playing' if play_now else 'Added to queue'}: {hist_item.title}",
            "track": {
                "source": "qqmusic",
                "track_id": f"qqmusic:{song_mid}",
                "song_mid": song_mid,
            },
        }

    raise HTTPException(status_code=400, detail=f"unsupported history source: {track_id}")


@app.post("/history/{history_id}/replay")
async def replay_from_history(
    history_id: int,
    play_now: bool = True,
    session: Session = Depends(get_session)
) -> dict:
    """Replay a track from history using its track_id to get a fresh playable source"""
    hist_item = session.get(HistoryItem, history_id)
    if not hist_item:
        raise HTTPException(status_code=404, detail="History item not found")

    try:
        return await _replay_history_item(hist_item, play_now=play_now, requested_by="web_history")
    except HTTPException as e:
        if e.status_code in (402, 403):
            raise HTTPException(
                status_code=e.status_code,
                detail=f"Cannot replay '{hist_item.title}': {e.detail}"
            )
        raise


@app.get("/external/status", tags=["External API"])
async def external_status(session: Session = Depends(get_session)) -> dict:
    status = await voice_status()
    queue_items = get_queue(session=session)
    status["queue_length"] = len(queue_items)
    status["queue_preview"] = queue_items[:10]
    return status


@app.post("/external/player/action", tags=["External API"])
async def external_player_action(req: ExternalPlayerActionRequest) -> dict:
    action_aliases = {
        "resume": "play",
        "continue": "play",
        "switch": "next",
    }
    action = action_aliases.get((req.action or "").strip().lower(), (req.action or "").strip().lower())
    if action == "play":
        return await voice_play()
    if action == "pause":
        return await voice_pause()
    if action == "next":
        return await voice_next()
    if action == "previous":
        return await voice_previous()
    if action == "skip":
        return await voice_skip()
    raise HTTPException(status_code=400, detail="unsupported action")


@app.put("/external/player/volume", tags=["External API"])
async def external_set_player_volume(
    req: VolumeUpdateRequest,
    session: Session = Depends(get_session),
) -> dict:
    return await set_voice_volume(req, session=session)


@app.post("/external/player/shuffle", tags=["External API"])
async def external_set_player_shuffle(req: ShuffleRequest) -> dict:
    return await voice_shuffle(req)


@app.post("/external/player/repeat", tags=["External API"])
async def external_set_player_repeat(req: RepeatRequest) -> dict:
    return await voice_repeat(req)


@app.get("/external/search", tags=["External API"])
async def external_search(
    keywords: str,
    source: str = "netease",
    limit: int = 20,
    page: int = 1,
) -> dict:
    query = (keywords or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="keywords is empty")

    provider = (source or "netease").strip().lower()
    page = max(1, int(page))
    limit = max(1, min(int(limit), 50))

    if provider == "bilibili":
        return await _bilibili_search_videos(keywords=query, limit=limit, page=page)

    if provider == "qqmusic":
        songs = await qqmusic.search_songs_simple(query, limit=limit, page=page)
        items = _normalize_qqmusic_search_items(songs)
        return {
            "source": provider,
            "keywords": query,
            "page": page,
            "limit": limit,
            "has_more": len(items) == limit,
            "items": items,
        }

    if provider != "netease":
        raise HTTPException(status_code=400, detail="unsupported source")

    offset = (page - 1) * limit
    result = await search(keywords=query, limit=limit, offset=offset)
    raw = result.raw
    total = _coerce_positive_int((((raw or {}).get("result") or {}).get("songCount")))
    items = _normalize_netease_search_items(raw)
    return {
        "source": provider,
        "keywords": query,
        "page": page,
        "limit": limit,
        "total": total,
        "has_more": (offset + len(items)) < total if total is not None else len(items) == limit,
        "items": items,
    }


@app.post("/external/queue", tags=["External API"])
async def external_add_queue(req: ExternalQueueRequest) -> dict:
    provider = (req.source or "netease").strip().lower()
    keywords = (req.keywords or "").strip()
    play_now = bool(req.play_now)

    if provider == "netease":
        song_id = (req.song_id or "").strip()
        title = (req.title or "").strip()
        artist = (req.artist or "").strip()
        album = (req.album or "").strip()
        cover_url = (req.cover_url or "").strip()
        duration_ms = req.duration_ms
        level = _normalize_netease_quality_level(req.level, strict=True)

        if not song_id:
            if not keywords:
                raise HTTPException(status_code=400, detail="song_id or keywords is required for netease")
            result = await search(keywords=keywords, limit=1, offset=0)
            items = _normalize_netease_search_items(result.raw)
            if not items:
                raise HTTPException(status_code=404, detail="netease song not found")
            first = items[0]
            song_id = str(first.get("song_id") or "").strip()
            title = title or str(first.get("title") or song_id).strip()
            artist = artist or str(first.get("artist") or "").strip()
            album = album or str(first.get("album") or "").strip()
            cover_url = cover_url or str(first.get("artwork_url") or "").strip()
            duration_ms = duration_ms if duration_ms is not None else _coerce_positive_int(first.get("duration_ms"))

        if song_id and (not title or not artist or not album or not cover_url or duration_ms is None):
            detail = await netease.song_detail(song_id=song_id)
            songs = (detail or {}).get("songs") or []
            if isinstance(songs, list) and songs and isinstance(songs[0], dict):
                normalized = _normalize_netease_song(songs[0])
                if normalized is not None:
                    title = title or str(normalized.get("title") or song_id).strip()
                    artist = artist or str(normalized.get("artist") or "").strip()
                    album = album or str(normalized.get("album") or "").strip()
                    cover_url = cover_url or str(normalized.get("artwork_url") or "").strip()
                    duration_ms = duration_ms if duration_ms is not None else _coerce_positive_int(normalized.get("duration_ms"))

        if not song_id:
            raise HTTPException(status_code=400, detail="song_id is empty")

        item_id, trial = await _enqueue_netease_song(
            song_id=song_id,
            title=title or song_id,
            artist=artist,
            play_now=play_now,
            requested_by="external_api",
            album=album,
            duration_ms=duration_ms,
            artwork_url=cover_url,
            quality_level=level,
        )
        return {
            "ok": True,
            "source": provider,
            "queue_id": item_id,
            "trial": trial,
            "play_now": play_now,
            "track": {
                "source": provider,
                "track_id": f"netease:{song_id}",
                "song_id": song_id,
                "title": title or song_id,
                "artist": artist,
                "album": album,
                "duration_ms": duration_ms,
                "artwork_url": cover_url,
                "level": level,
            },
        }

    if provider == "bilibili":
        video_id = _extract_bilibili_video_id(req.video_id)
        title = (req.title or "").strip()
        artist = (req.artist or "").strip()
        album = (req.album or "").strip()
        duration_ms = req.duration_ms
        cover_url = (req.cover_url or "").strip()

        if not video_id:
            if not keywords:
                raise HTTPException(status_code=400, detail="video_id or keywords is required for bilibili")
            result = await _bilibili_search_videos(keywords=keywords, limit=1, page=1)
            items = result.get("items") or []
            if not items:
                raise HTTPException(status_code=404, detail="bilibili video not found")
            first = items[0]
            video_id = _extract_bilibili_video_id(first.get("video_id"))
            title = title or str(first.get("title") or video_id).strip()
            artist = artist or str(first.get("artist") or "").strip()
            album = album or str(first.get("album") or "").strip()
            cover_url = cover_url or str(first.get("artwork_url") or "").strip()
            duration_ms = duration_ms if duration_ms is not None else _coerce_positive_int(first.get("duration_ms"))

        if video_id and (not title or not artist or not album or not cover_url or duration_ms is None):
            metadata = await _extract_bilibili_video_info(video_id)
            title = title or str(metadata.get("title") or video_id).strip()
            artist = artist or str(metadata.get("artist") or "").strip()
            album = album or str(metadata.get("album") or "").strip()
            cover_url = cover_url or str(metadata.get("artwork_url") or "").strip()
            duration_ms = duration_ms if duration_ms is not None else _coerce_positive_int(metadata.get("duration_ms"))

        if not video_id:
            raise HTTPException(status_code=400, detail="video_id is empty")

        item_id, trial = await _enqueue_bilibili_song(
            video_id=video_id,
            title=title or video_id,
            artist=artist,
            play_now=play_now,
            requested_by="external_api",
            album=album,
            duration_ms=duration_ms,
            artwork_url=cover_url,
        )
        return {
            "ok": True,
            "source": provider,
            "queue_id": item_id,
            "trial": trial,
            "play_now": play_now,
            "track": {
                "source": provider,
                "track_id": f"bilibili:{video_id}",
                "video_id": video_id,
                "title": title or video_id,
                "artist": artist,
                "album": album,
                "duration_ms": duration_ms,
                "artwork_url": cover_url,
                "webpage_url": _build_bilibili_video_url(video_id),
            },
        }

    if provider == "qqmusic":
        song_mid = (req.song_mid or "").strip()
        title = (req.title or "").strip()
        artist = (req.artist or "").strip()
        album = (req.album or "").strip()
        album_mid = (req.album_mid or "").strip()
        duration_ms = req.duration_ms
        quality = (req.quality or "320").strip() or "320"
        cover_url = (req.cover_url or "").strip()

        if not song_mid:
            if not keywords:
                raise HTTPException(status_code=400, detail="song_mid or keywords is required for qqmusic")
            songs = await qqmusic.search_songs_simple(keywords, limit=1, page=1)
            items = _normalize_qqmusic_search_items(songs)
            if not items:
                raise HTTPException(status_code=404, detail="qqmusic song not found")
            first = items[0]
            song_mid = str(first.get("song_mid") or "").strip()
            title = title or str(first.get("title") or song_mid).strip()
            artist = artist or str(first.get("artist") or "").strip()
            album = album or str(first.get("album") or "").strip()
            album_mid = album_mid or str(first.get("album_mid") or "").strip()
            cover_url = cover_url or str(first.get("artwork_url") or "").strip()
            duration_ms = duration_ms if duration_ms is not None else _coerce_positive_int(first.get("duration_ms"))

        if not song_mid:
            raise HTTPException(status_code=400, detail="song_mid is empty")
        if not title:
            raise HTTPException(status_code=400, detail="title is required for qqmusic")
        if not cover_url and album_mid:
            cover_url = qqmusic.get_song_cover_image(album_mid)

        item_id, trial = await _enqueue_qqmusic_song(
            song_mid=song_mid,
            title=title,
            artist=artist,
            play_now=play_now,
            requested_by="external_api",
            quality=quality,
            album_mid=album_mid,
            duration_ms=duration_ms,
        )
        return {
            "ok": True,
            "source": provider,
            "queue_id": item_id,
            "trial": trial,
            "play_now": play_now,
            "track": {
                "source": provider,
                "track_id": f"qqmusic:{song_mid}",
                "song_mid": song_mid,
                "title": title,
                "artist": artist,
                "album": album,
                "album_mid": album_mid,
                "duration_ms": duration_ms,
                "artwork_url": cover_url,
                "quality": quality,
            },
        }

    raise HTTPException(status_code=400, detail="unsupported source")


@app.get("/external/queue", tags=["External API"])
def external_get_queue(session: Session = Depends(get_session)) -> dict:
    items = get_queue(session=session)
    return {"count": len(items), "items": items}


@app.delete("/external/queue", tags=["External API"])
async def external_clear_queue(session: Session = Depends(get_session)) -> dict:
    return await clear_queue(session=session)


@app.delete("/external/queue/{item_id}", tags=["External API"])
def external_delete_queue_item(item_id: int, session: Session = Depends(get_session)) -> dict:
    return delete_queue_item(item_id=item_id, session=session)


@app.post("/external/queue/{item_id}/play", tags=["External API"])
async def external_play_queue_item(item_id: int, session: Session = Depends(get_session)) -> dict:
    return await play_queue_item(item_id=item_id, session=session)


@app.get("/external/history", tags=["External API"])
def external_history(session: Session = Depends(get_session)) -> dict:
    items = history(session=session)
    return {"count": len(items), "items": items}


@app.post("/external/history/{history_id}/replay", tags=["External API"])
async def external_replay_history(
    history_id: int,
    play_now: bool = True,
    session: Session = Depends(get_session),
) -> dict:
    hist_item = session.get(HistoryItem, history_id)
    if not hist_item:
        raise HTTPException(status_code=404, detail="History item not found")
    return await _replay_history_item(hist_item, play_now=play_now, requested_by="external_history")


# 网易云音乐扩展功能 API

@app.get("/netease/search/suggest")
async def netease_search_suggest(keywords: str) -> dict:
    """搜索建议"""
    try:
        result = await netease.search_suggest(keywords)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/search/hot")
async def netease_search_hot() -> dict:
    """热搜列表"""
    try:
        result = await netease.search_hot()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/search/default")
async def netease_search_default() -> dict:
    """默认搜索关键词"""
    try:
        result = await netease.search_default()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/playlist/categories")
async def netease_playlist_categories() -> dict:
    """歌单分类"""
    try:
        result = await netease.playlist_catlist()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/playlist/hot")
async def netease_playlist_hot_categories() -> dict:
    """热门歌单分类"""
    try:
        result = await netease.playlist_hot()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/playlist/top")
async def netease_top_playlists(cat: str = "全部", limit: int = 50, offset: int = 0) -> dict:
    """网友精选歌单"""
    try:
        result = await netease.top_playlist(cat=cat, limit=limit, offset=offset)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/playlist/highquality")
async def netease_highquality_playlists(cat: str = "全部", limit: int = 20) -> dict:
    """精品歌单"""
    try:
        result = await netease.top_playlist_highquality(cat=cat, limit=limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/playlist/{playlist_id}/detail")
async def netease_playlist_detail(playlist_id: str) -> dict:
    """歌单详情"""
    try:
        cookie = _get_admin_cookie_or_none()
        result = await netease.playlist_detail(playlist_id, cookie=cookie)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/song/{song_id}/lyric")
async def netease_song_lyric(song_id: str) -> dict:
    """获取歌词"""
    try:
        cookie = _get_admin_cookie_or_none()
        result = await netease.lyric(song_id, cookie=cookie)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/recommend/playlists")
async def netease_recommend_playlists(limit: int = 30) -> dict:
    """推荐歌单"""
    try:
        cookie = _get_admin_cookie_or_none()
        result = await netease.personalized(limit=limit, cookie=cookie)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_admin_cookie_or_none() -> str | None:
    """获取管理员Cookie，如果不存在则返回None"""
    try:
        session = new_session()
        try:
            return _get_admin_cookie(session)
        finally:
            session.close()
    except HTTPException:
        return None


def _get_admin_bilibili_cookie_or_none() -> str | None:
    try:
        session = new_session()
        try:
            return _get_admin_bilibili_cookie(session)
        finally:
            session.close()
    except HTTPException:
        return None


# QQ 音乐 API 端点

@app.get("/bilibili/search/videos")
async def bilibili_search_videos(keywords: str, limit: int = 20, page: int = 1) -> dict:
    try:
        return await _bilibili_search_videos(keywords=keywords, limit=limit, page=page)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/search")
async def qqmusic_search(keywords: str, search_type: int = 0, limit: int = 50, page: int = 1) -> dict:
    """QQ音乐搜索"""
    try:
        result = await qqmusic.search_with_keyword(keywords, search_type, limit, page)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/search/songs")
async def qqmusic_search_songs(keywords: str, limit: int = 50, page: int = 1) -> dict:
    """QQ音乐搜索歌曲（简化版）"""
    try:
        songs = await qqmusic.search_songs_simple(keywords, limit, page)
        return {"songs": songs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/song/{song_mid}/url")
async def qqmusic_song_url(song_mid: str, quality: str = "320") -> dict:
    """获取QQ音乐播放URL"""
    try:
        data = await qqmusic.get_music_url(song_mid, quality)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/song/{song_mid}/lyric")
async def qqmusic_song_lyric(song_mid: str, parse: bool = False) -> dict:
    """获取QQ音乐歌词"""
    try:
        if parse:
            data = await qqmusic.get_song_lyric(song_mid)
            parsed = qqmusic.parse_lyric(data)
            return {"lyric": parsed}
        else:
            lyric = await qqmusic.get_song_lyric_simple(song_mid)
            return {"lyric": lyric}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/playlist/{playlist_id}")
async def qqmusic_playlist_detail(playlist_id: str) -> dict:
    """获取QQ音乐歌单详情"""
    try:
        data = await qqmusic.get_song_list(playlist_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/playlist/{playlist_id}/songs")
async def qqmusic_playlist_songs(playlist_id: str) -> dict:
    """获取QQ音乐歌单歌曲列表（简化版）"""
    try:
        songs = await qqmusic.get_song_list_simple(playlist_id)
        return {"songs": songs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/playlist/{playlist_id}/name")
async def qqmusic_playlist_name(playlist_id: str) -> dict:
    """获取QQ音乐歌单名称"""
    try:
        name = await qqmusic.get_song_list_name_simple(playlist_id)
        return {"name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/album/{album_mid}")
async def qqmusic_album_detail(album_mid: str) -> dict:
    """获取QQ音乐专辑详情"""
    try:
        data = await qqmusic.get_album_song_list(album_mid)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/album/{album_mid}/name")
async def qqmusic_album_name(album_mid: str) -> dict:
    """获取QQ音乐专辑名称"""
    try:
        data = await qqmusic.get_album_name(album_mid)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/singer/{singer_mid}")
async def qqmusic_singer_info(singer_mid: str) -> dict:
    """获取QQ音乐歌手信息"""
    try:
        data = await qqmusic.get_singer_info(singer_mid)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/mv/{vid}")
async def qqmusic_mv_info(vid: str) -> dict:
    """获取QQ音乐MV信息"""
    try:
        data = await qqmusic.get_mv_info(vid)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/album/{album_mid}/cover")
async def qqmusic_album_cover(album_mid: str) -> dict:
    """获取QQ音乐专辑封面URL"""
    try:
        cover_url = qqmusic.get_album_cover_image(album_mid)
        return {"cover_url": cover_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# QQ Music Login endpoints

@app.get("/qqmusic/login/qr/key")
async def qqmusic_qr_key() -> dict:
    """获取QQ音乐二维码登录密钥"""
    try:
        return await qqmusic.get_qr_key()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/login/qr/check")
async def qqmusic_qr_check(qr_key: str, ptqrtoken: str, pt_login_sig: str = "") -> dict:
    """检查QQ音乐二维码登录状态"""
    try:
        # Set the pt_login_sig in the client if provided
        if pt_login_sig:
            qqmusic._pt_login_sig = pt_login_sig
        return await qqmusic.check_qr_status(qr_key, ptqrtoken)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class QQMusicCookieSetRequest(BaseModel):
    cookie: str


class QQMusicQRConfirmRequest(BaseModel):
    auth_url: str


@app.get("/admin/qqmusic/status")
async def admin_qqmusic_status(request: Request, session: Session = Depends(get_session)) -> dict:
    _require_admin_token(request)
    row = session.get(Secret, "qqmusic_cookie")
    return {"admin_cookie_set": bool(row and row.value)}


@app.post("/admin/qqmusic/cookie")
async def admin_qqmusic_set_cookie(
    req: QQMusicCookieSetRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    _require_admin_token(request)
    c = (req.cookie or "").strip()
    if not c:
        raise HTTPException(status_code=400, detail="cookie is empty")
    if c.lower().startswith("cookie:"):
        c = c.split(":", 1)[1].strip()
    c = c.replace("\r", "").replace("\n", "")
    _set_secret(session, "qqmusic_cookie", c)
    qqmusic.set_cookie(c)
    return {"ok": True, "admin_cookie_set": True, "uin": qqmusic.get_uin()}


@app.post("/admin/qqmusic/qr/confirm")
async def admin_qqmusic_qr_confirm(
    req: QQMusicQRConfirmRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """管理员扫码成功后确认登录，获取并保存最终 cookies"""
    _require_admin_token(request)
    r = await qqmusic.confirm_qr_login(req.auth_url)
    c = (qqmusic.get_cookie() or "").strip()
    print(f"[DEBUG] QR confirm - new cookie length: {len(c)}, preview: {c[:200]}...")
    if c:
        _set_secret(session, "qqmusic_cookie", c)
        print(f"[DEBUG] QR confirm - cookie saved to database")
    else:
        print(f"[DEBUG] QR confirm - no cookie to save")
    return {"ok": True, "admin_cookie_set": bool(c), "uin": qqmusic.get_uin(), "raw": r}


@app.get("/admin/bilibili/status")
async def admin_bilibili_status(request: Request, session: Session = Depends(get_session)) -> dict:
    _require_admin_token(request)
    row = session.get(Secret, "bilibili_cookie")
    return {
        "admin_cookie_set": bool(row and row.value),
        "playwright_available": await is_playwright_runtime_available(),
        "playwright_dependency_installed": is_playwright_available(),
    }


@app.get("/admin/bilibili/account")
async def admin_bilibili_account(request: Request, session: Session = Depends(get_session)) -> dict:
    _require_admin_token(request)
    cookie = _get_admin_bilibili_cookie(session)
    data = await asyncio.to_thread(_fetch_bilibili_nav_sync, cookie)
    return {
        "mid": data.get("mid"),
        "uname": data.get("uname") or "",
        "level_info": data.get("level_info") or {},
        "is_login": bool(data.get("isLogin")),
    }


@app.post("/admin/bilibili/cookie")
async def admin_bilibili_set_cookie(
    req: AdminCookieSetRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    _require_admin_token(request)
    c = (req.cookie or "").strip()
    if not c:
        raise HTTPException(status_code=400, detail="cookie is empty")
    if c.lower().startswith("cookie:"):
        c = c.split(":", 1)[1].strip()
    c = c.replace("\r", "").replace("\n", "")
    nav = await asyncio.to_thread(_fetch_bilibili_nav_sync, c)
    if not bool(nav.get("isLogin")):
        raise HTTPException(status_code=400, detail="bilibili cookie is not logged in")
    _set_secret(session, "bilibili_cookie", c)
    return {
        "ok": True,
        "admin_cookie_set": True,
        "mid": nav.get("mid"),
        "uname": nav.get("uname") or "",
    }


@app.post("/admin/bilibili/qr/start")
async def admin_bilibili_qr_start(request: Request) -> dict:
    _require_admin_token(request)
    try:
        return await start_bilibili_qr_login_session()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/admin/bilibili/qr/check")
async def admin_bilibili_qr_check(
    session_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    _require_admin_token(request)
    try:
        result = await poll_bilibili_qr_login_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.get("status") == "authorized":
        cookie = str(result.get("cookie") or "").strip()
        if cookie:
            _set_secret(session, "bilibili_cookie", cookie)
            try:
                nav = await asyncio.to_thread(_fetch_bilibili_nav_sync, cookie)
            except Exception as exc:
                logger.warning("failed to fetch bilibili account after qr auth: %s", exc)
                nav = {}
            return {
                "status": "authorized",
                "code": result.get("code"),
                "message": result.get("message"),
                "admin_cookie_set": True,
                "mid": nav.get("mid"),
                "uname": nav.get("uname") or "",
            }
        return {
            "status": "authorized",
            "code": result.get("code"),
            "message": "扫码已确认，但未拿到完整登录 Cookie，请重试一次",
            "admin_cookie_set": False,
        }

    return {
        "status": result.get("status"),
        "code": result.get("code"),
        "message": result.get("message"),
        "admin_cookie_set": False,
        "raw": result.get("raw"),
    }


@app.post("/qqmusic/login/cookie")
async def qqmusic_set_cookie(req: QQMusicCookieSetRequest) -> dict:
    """设置QQ音乐Cookie"""
    try:
        qqmusic.set_cookie(req.cookie)
        return {"success": True, "message": "Cookie设置成功", "uin": qqmusic.get_uin()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/login/status")
async def qqmusic_login_status() -> dict:
    """获取QQ音乐登录状态"""
    try:
        if not qqmusic.get_cookie():
            return {"logged_in": False, "message": "未设置Cookie"}
        
        refresh_result = await qqmusic.refresh_login()
        return {
            "logged_in": refresh_result["success"],
            "message": refresh_result["message"],
            "uin": qqmusic.get_uin(),
            "cookie": qqmusic.get_cookie()
        }
    except Exception as e:
        return {"logged_in": False, "message": str(e)}


@app.get("/qqmusic/user/info")
async def qqmusic_user_info() -> dict:
    """获取QQ音乐用户信息"""
    try:
        return await qqmusic.get_user_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qqmusic/user/playlists")
async def qqmusic_user_playlists() -> dict:
    """获取QQ音乐用户歌单"""
    try:
        return await qqmusic.get_user_playlists()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/qqmusic/login/refresh")
async def qqmusic_refresh_login() -> dict:
    """刷新QQ音乐登录状态"""
    try:
        return await qqmusic.refresh_login()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
