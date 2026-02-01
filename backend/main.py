from __future__ import annotations

import asyncio
from collections import deque
import hashlib
import os
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .crypto import decrypt_text, encrypt_text
from .db import create_db_and_tables, get_session, new_session
from .models import HistoryItem, QueueItem, Secret
from .netease import NeteaseClient
from .voice_client import VoiceClient
from .config import settings
from .logger import logger

app = FastAPI(title="tsbot-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

netease = NeteaseClient()
voice = VoiceClient()

_chat_task: asyncio.Task[None] | None = None
_current_queue_item_id: int | None = None
_current_source_url: str = ""
_playback_lock = asyncio.Lock()
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


def _resolve_playback_position_s(*, now_s: float, started_at: float, paused_at: float | None, paused_total_s: float) -> float:
    if paused_at is not None:
        pos = paused_at - started_at - paused_total_s
    else:
        pos = now_s - started_at - paused_total_s
    return max(0.0, pos)


async def _play_queue_item_internal(item_id: int, *, requested_by: str) -> bool:
    session = new_session()
    try:
        item = session.get(QueueItem, item_id)
        if not item:
            return False

        notice = ""
        duration_ms: int | None = None
        artist = str(item.artist or "")
        album = ""
        artwork_url = ""
        if item.track_id.startswith("netease:"):
            cookie = _get_admin_cookie(session)
            song_id = item.track_id.split(":", 1)[1]
            notice, duration_ms, artist2, album2, artwork2 = await _netease_notice_and_duration(song_id, cookie)
            if artist2:
                artist = artist2
            album = album2
            artwork_url = artwork2

            # Re-resolve a fresh URL at play time to avoid CDN "expired url".
            data = await netease.song_url(song_id=song_id, cookie=cookie)
            try:
                url = _resolve_netease_song_url(data)
            except HTTPException as e:
                if e.status_code == 402:
                    trial_data = await netease.song_url(song_id=song_id, cookie=cookie, br=128000)
                    url = _resolve_netease_song_url(trial_data)
                else:
                    raise

            item.source_url = url
            item.album = album
            item.duration = duration_ms
            item.cover_url = artwork_url
            if artist:
                item.artist = artist

            session.add(item)
            session.commit()

        await _set_now_playing_queue_item(
            int(item.id),
            item.source_url,
            duration_ms=duration_ms,
            artist=artist,
            album=album,
            artwork_url=artwork_url,
        )
        await voice.play(source_url=item.source_url, title=item.title, requested_by=requested_by, notice=notice)

        hist = HistoryItem(
            track_id=item.track_id,
            title=item.title,
            artist=item.artist,
            source_url=item.source_url,
            requested_by=requested_by,
        )
        session.add(hist)
        session.commit()
        return True
    finally:
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
        await _auto_play_next_from_queue()
        return {"ok": True, "action": "play_next"}
    if cur == "STATE_PAUSED":
        await _mark_playback_resumed()
        await voice.resume()
        return {"ok": True, "action": "resume"}
    return {"ok": True, "action": "noop"}


@app.post("/voice/pause")
async def voice_pause() -> dict:
    await _mark_playback_paused()
    await voice.pause()
    return {"ok": True}


@app.post("/voice/next")
async def voice_next() -> dict:
    global _current_shuffle_index, _shuffle_queue
    current_item_id = None
    async with _playback_lock:
        current_item_id = _current_queue_item_id

    if current_item_id:
        await _remove_queue_item_internal(current_item_id)

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
        async with _playback_lock:
            start_after_id = _current_queue_item_id
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
    async with _playback_lock:
        current_item_id = _current_queue_item_id
    
    if current_item_id:
        # Remove current song from queue
        await _remove_queue_item_internal(current_item_id)
        
        # Stop current playback
        await _set_now_playing_queue_item(None)
        await voice.skip()
        
        # Auto play next song
        await _auto_play_next_from_queue(start_after_id=current_item_id)
        return {"ok": True, "action": "skipped_and_next", "removed_track_id": current_item_id}
    else:
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
            if _current_queue_item_id:
                prev = session.execute(
                    select(QueueItem)
                    .where(QueueItem.id < _current_queue_item_id)
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
    # Note: Seek functionality may not be implemented in voice client
    return {"ok": True, "message": "Seek not implemented", "time": req.time}


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
async def search(keywords: str, limit: int = 20) -> SearchResponse:
    data = await netease.search(keywords=keywords, limit=limit)
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
    finally:
        session.close()

    if not track_id.startswith("netease:"):
        return LyricsResponse(lyrics=[])

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


def _resolve_netease_song_url(data: dict) -> str:
    code = (data or {}).get("code")
    if code not in (None, 200):
        raise HTTPException(status_code=502, detail=f"netease api error: code={code}")

    items = (data or {}).get("data") or []
    if not items:
        raise HTTPException(status_code=502, detail="netease api error: empty data")

    it = (items[0] or {}) if isinstance(items, list) else {}
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


@app.get("/netease/song/url")
async def song_url(id: str, session: Session = Depends(get_session)) -> dict:
    cookie = _get_admin_cookie(session)
    data = await netease.song_url(song_id=id, cookie=cookie)
    try:
        url = _resolve_netease_song_url(data)
        return {"url": url, "trial": False}
    except HTTPException as e:
        if e.status_code == 402:
            trial_data = await netease.song_url(song_id=id, cookie=cookie, br=128000)
            url = _resolve_netease_song_url(trial_data)
            return {"url": url, "trial": True}
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
        return decrypt_text(row.value)
    except Exception:
        raise HTTPException(status_code=500, detail="failed to decrypt admin netease cookie")


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
        "fx pan <-1..1> / fx width <0..3> / fx swap <on|off> / fx bass <0..18> / fx reverb <0..1> / fx reset"
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
) -> tuple[int, bool]:
    session = new_session()
    try:
        cookie = _get_admin_cookie(session)
        notice, duration_ms, artist2, album, artwork_url = await _netease_notice_and_duration(song_id, cookie)
        data = await netease.song_url(song_id=song_id, cookie=cookie)
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

        item = QueueItem(
            track_id=f"netease:{song_id}",
            title=title,
            artist=artist,
            album=album,
            duration=duration_ms,
            cover_url=artwork_url,
            source_url=url,
        )
        session.add(item)
        session.commit()

        _schedule_ts_description_update()

        if play_now:
            await _set_now_playing_queue_item(
                int(item.id),
                url,
                duration_ms=duration_ms,
                artist=artist2 or artist,
                album=album,
                artwork_url=artwork_url,
            )
            await voice.play(source_url=url, title=title, requested_by=requested_by, notice=notice)
            hist = HistoryItem(
                track_id=item.track_id,
                title=title,
                artist=artist,
                album=album,
                duration=duration_ms,
                cover_url=artwork_url,
                source_url=url,
                requested_by=requested_by,
            )
            session.add(hist)
            session.commit()

        return int(item.id), trial
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
    }

    cmd = alias_to_cmd.get(head_norm)
    if not cmd:
        return
    arg = tail.strip()

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
            await _mark_playback_resumed()
            await voice.resume()
            await reply("已恢复")
            return

        if cmd == "stop":
            await _set_now_playing_queue_item(None)
            await voice.stop()
            await reply("已停止")
            return

        if cmd == "skip":
            # Get current playing item to remove it
            current_item_id = None
            async with _playback_lock:
                current_item_id = _current_queue_item_id
            
            if current_item_id:
                # Remove current song from queue
                await _remove_queue_item_internal(current_item_id)
                
                # Stop current playback
                await _set_now_playing_queue_item(None)
                await voice.skip()
                
                # Auto play next song
                await _auto_play_next_from_queue()
                await reply("已跳过当前歌曲并播放下一首")
            else:
                await reply("当前没有正在播放的歌曲")
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

        if cmd == "search":
            if not arg:
                await reply("用法: search <关键词>")
                return
            raw = await netease.search(keywords=arg, limit=5)
            songs = (((raw or {}).get("result") or {}).get("songs") or [])
            if not songs:
                await reply("没有找到结果")
                return
            lines: list[str] = []
            for i, s in enumerate(songs[:5], start=1):
                sid = str((s or {}).get("id") or "")
                title = str((s or {}).get("name") or "")
                artist = ", ".join([str(a.get("name") or "") for a in ((s or {}).get("ar") or []) if isinstance(a, dict)])
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
    return {"admin_cookie_set": bool(row and row.value)}


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
    return {
        "cwd": os.getcwd(),
        "sqlite_db_path": str(Path("./tsbot.db").resolve()),
    }


@app.get("/admin/debug/song_url")
async def admin_debug_song_url(id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    _require_admin_token(request)
    cookie = _get_admin_cookie(session)

    detail = await netease.song_detail(song_id=id, cookie=cookie)
    dt = _resolve_netease_duration_ms(detail)

    data = await netease.song_url(song_id=id, cookie=cookie)
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

    it = {}
    items = (data or {}).get("data") or []
    if isinstance(items, list) and items:
        it = items[0] or {}

    return {
        "song_id": id,
        "trial": trial,
        "duration_ms": dt,
        "url": url,
        "song_url_item": {
            "code": it.get("code"),
            "fee": it.get("fee"),
            "payed": it.get("payed"),
            "level": it.get("level"),
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
    _set_secret(session, "netease_cookie", c)
    return {"ok": True, "admin_cookie_set": True}


@app.get("/admin/qr/key")
async def admin_qr_key() -> dict:
    return await netease.qr_key()


@app.get("/admin/qr/create")
async def admin_qr_create(key: str) -> dict:
    return await netease.qr_create(key)


@app.get("/admin/qr/check")
async def admin_qr_check(key: str, session: Session = Depends(get_session)) -> dict:
    data = await netease.qr_check(key)
    code = (data or {}).get("code")
    cookie = (data or {}).get("cookie") or ""
    if code == 803 and cookie:
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


class AddQueueNeteaseRequest(BaseModel):
    song_id: str
    title: str
    artist: str
    play_now: bool = False


@app.post("/queue/netease")
async def add_queue_netease(req: AddQueueNeteaseRequest) -> dict:
    try:
        item_id, trial = await _enqueue_netease_song(
            song_id=req.song_id,
            title=req.title,
            artist=req.artist,
            play_now=req.play_now,
            requested_by="web",
        )
        return {"ok": True, "id": item_id, "trial": trial}
    except Exception as e:
        logger.error(f"Failed to enqueue netease song {req.song_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/queue")
def get_queue(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(select(QueueItem).order_by(QueueItem.id.asc())).scalars().all()
    return [
        {
            "id": r.id,
            "track_id": r.track_id,
            "title": r.title,
            "artist": r.artist,
            "album": r.album,
            "duration": r.duration / 1000.0 if r.duration else None,
            "artwork": r.cover_url,
            "source_url": r.source_url,
        }
        for r in rows
    ]


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
    return [
        {
            "id": r.id,
            "played_at": r.played_at.isoformat(),
            "track_id": r.track_id,
            "title": r.title,
            "artist": r.artist,
            "album": r.album,
            "duration": r.duration / 1000.0 if r.duration else None,
            "artwork": r.cover_url,
            "source_url": r.source_url,
            "requested_by": r.requested_by,
        }
        for r in rows
    ]


@app.post("/history/{history_id}/replay")
async def replay_from_history(
    history_id: int,
    play_now: bool = True,
    session: Session = Depends(get_session)
) -> dict:
    """Replay a track from history using its track_id to get fresh URL"""
    hist_item = session.get(HistoryItem, history_id)
    if not hist_item:
        raise HTTPException(status_code=404, detail="History item not found")
    
    track_id = hist_item.track_id
    if not track_id.startswith("netease:"):
        raise HTTPException(status_code=400, detail="Only netease tracks can be replayed")
    
    song_id = track_id.split(":", 1)[1]
    
    # Use the existing _enqueue_netease_song function to get fresh URL
    try:
        item_id, trial = await _enqueue_netease_song(
            song_id=song_id,
            title=hist_item.title,
            artist=hist_item.artist,
            play_now=play_now,
            requested_by="web_history",
        )
        return {
            "ok": True,
            "queue_id": item_id,
            "trial": trial,
            "message": f"{'Playing' if play_now else 'Added to queue'}: {hist_item.title}"
        }
    except HTTPException as e:
        # If the song is no longer available, return a helpful error
        if e.status_code in (402, 403):
            raise HTTPException(
                status_code=e.status_code,
                detail=f"Cannot replay '{hist_item.title}': {e.detail}"
            )
        raise


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
async def netease_playlist_detail(playlist_id: str, request: Request) -> dict:
    """歌单详情"""
    try:
        cookie = _get_admin_cookie_or_none(request)
        result = await netease.playlist_detail(playlist_id, cookie=cookie)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/song/{song_id}/lyric")
async def netease_song_lyric(song_id: str, request: Request) -> dict:
    """获取歌词"""
    try:
        cookie = _get_admin_cookie_or_none(request)
        result = await netease.lyric(song_id, cookie=cookie)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/netease/recommend/playlists")
async def netease_recommend_playlists(request: Request, limit: int = 30) -> dict:
    """推荐歌单"""
    try:
        cookie = _get_admin_cookie_or_none(request)
        result = await netease.personalized(limit=limit, cookie=cookie)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_admin_cookie_or_none(request: Request) -> str | None:
    """获取管理员Cookie，如果不存在则返回None"""
    try:
        return _get_admin_cookie(request)
    except HTTPException:
        return None


