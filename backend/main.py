from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
from .config import settings
from .crypto import decrypt_text, encrypt_text
from .db import create_db_and_tables, get_session, new_session
from .models import HistoryItem, Like, QueueItem, Secret, User, UserSecret
from .netease import NeteaseClient
from .voice_client import VoiceClient

app = FastAPI(title="tsbot-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

netease = NeteaseClient()
voice = VoiceClient()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class SearchResponse(BaseModel):
    raw: dict


class AddQueueRequest(BaseModel):
    track_id: str
    title: str
    artist: str = ""
    source_url: str


class CookieUpdateRequest(BaseModel):
    cookie: str


@app.on_event("startup")
def _startup() -> None:
    create_db_and_tables()
    session = new_session()
    try:
        admin = session.execute(select(User).where(User.username == settings.admin_username)).scalar_one_or_none()
        if not admin:
            admin = User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
            session.add(admin)
            session.commit()
    finally:
        session.close()


@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.execute(select(User).where(User.username == req.username)).scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return TokenResponse(access_token=create_access_token(user))


@app.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    exists = session.execute(select(User).where(User.username == req.username)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="username already exists")
    user = User(username=req.username, password_hash=hash_password(req.password), role="user")
    session.add(user)
    session.commit()
    return TokenResponse(access_token=create_access_token(user))


@app.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role}


@app.get("/me/likes")
def my_likes(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(select(Like).where(Like.user_id == user.id).order_by(Like.id.desc())).scalars().all()
    return [
        {"id": r.id, "track_id": r.track_id, "title": r.title, "artist": r.artist}
        for r in rows
    ]


class LikeCreateRequest(BaseModel):
    track_id: str
    title: str
    artist: str = ""


@app.post("/me/likes")
def add_like(req: LikeCreateRequest, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    like = Like(user_id=user.id, track_id=req.track_id, title=req.title, artist=req.artist)
    session.add(like)
    session.commit()
    return {"ok": True}


@app.delete("/me/likes/{like_id}")
def delete_like(like_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    like = session.get(Like, like_id)
    if not like or like.user_id != user.id:
        raise HTTPException(status_code=404, detail="not found")
    session.delete(like)
    session.commit()
    return {"ok": True}


@app.get("/search", response_model=SearchResponse)
async def search(keywords: str, limit: int = 20, user: User = Depends(get_current_user)) -> SearchResponse:
    data = await netease.search(keywords=keywords, limit=limit)
    return SearchResponse(raw=data)


@app.get("/playlist/detail")
async def playlist_detail(id: str, user: User = Depends(get_current_user)) -> dict:
    return await netease.playlist_detail(playlist_id=id)


@app.get("/me/netease/song/url")
async def my_song_url(id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    cookie = _get_user_cookie(session, user.id)
    return await netease.song_url(song_id=id, cookie=cookie)


def _get_user_cookie(session: Session, user_id: int) -> str:
    row = session.execute(
        select(UserSecret).where(UserSecret.user_id == user_id, UserSecret.key == "netease_cookie")
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=400, detail="netease cookie not set")
    return decrypt_text(row.value)


@app.get("/me/netease/cookie")
def get_my_cookie(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    row = session.execute(
        select(UserSecret).where(UserSecret.user_id == user.id, UserSecret.key == "netease_cookie")
    ).scalar_one_or_none()
    if not row:
        return {"cookie": ""}
    return {"cookie": decrypt_text(row.value)}


@app.put("/me/netease/cookie")
def set_my_cookie(
    req: CookieUpdateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    enc = encrypt_text(req.cookie)
    row = session.execute(
        select(UserSecret).where(UserSecret.user_id == user.id, UserSecret.key == "netease_cookie")
    ).scalar_one_or_none()
    if not row:
        row = UserSecret(user_id=user.id, key="netease_cookie", value=enc)
        session.add(row)
    else:
        row.value = enc
    session.commit()
    return {"ok": True}


@app.get("/me/netease/account")
async def my_account(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    cookie = _get_user_cookie(session, user.id)
    return await netease.user_account(cookie=cookie)


@app.get("/me/netease/likelist")
async def my_likelist(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    cookie = _get_user_cookie(session, user.id)
    account = await netease.user_account(cookie=cookie)
    profile = (account or {}).get("profile") or {}
    uid = profile.get("userId")
    if not uid:
        raise HTTPException(status_code=400, detail="unable to determine uid from cookie")
    return await netease.likelist(uid=str(uid), cookie=cookie)


@app.get("/me/netease/playlists")
async def my_playlists(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    cookie = _get_user_cookie(session, user.id)
    account = await netease.user_account(cookie=cookie)
    profile = (account or {}).get("profile") or {}
    uid = profile.get("userId")
    if not uid:
        raise HTTPException(status_code=400, detail="unable to determine uid from cookie")
    return await netease.user_playlist(uid=str(uid), cookie=cookie)


@app.get("/queue")
def get_queue(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(select(QueueItem).order_by(QueueItem.id.asc())).scalars().all()
    return [
        {
            "id": r.id,
            "track_id": r.track_id,
            "title": r.title,
            "artist": r.artist,
            "source_url": r.source_url,
        }
        for r in rows
    ]


@app.post("/queue")
def add_queue(req: AddQueueRequest, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    item = QueueItem(
        track_id=req.track_id,
        title=req.title,
        artist=req.artist,
        source_url=req.source_url,
        requested_by_user_id=user.id,
    )
    session.add(item)
    session.commit()
    return {"ok": True, "id": item.id}


@app.post("/queue/{item_id}/play")
async def play_queue_item(item_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    item = session.get(QueueItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="not found")

    await voice.play(source_url=item.source_url, title=item.title, requested_by=user.username)

    hist = HistoryItem(
        track_id=item.track_id,
        title=item.title,
        artist=item.artist,
        source_url=item.source_url,
        requested_by=user.username,
    )
    session.add(hist)
    session.commit()
    return {"ok": True}


@app.get("/history")
def history(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.execute(select(HistoryItem).order_by(HistoryItem.id.desc()).limit(200)).scalars().all()
    return [
        {
            "id": r.id,
            "played_at": r.played_at.isoformat(),
            "track_id": r.track_id,
            "title": r.title,
            "artist": r.artist,
            "source_url": r.source_url,
            "requested_by": r.requested_by,
        }
        for r in rows
    ]


@app.get("/admin/cookie")
def get_cookie(admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> dict:
    row = session.get(Secret, "netease_cookie")
    if not row:
        return {"cookie": ""}
    return {"cookie": decrypt_text(row.value)}


@app.put("/admin/cookie")
def set_cookie(req: CookieUpdateRequest, admin: User = Depends(require_admin), session: Session = Depends(get_session)) -> dict:
    row = session.get(Secret, "netease_cookie")
    enc = encrypt_text(req.cookie)
    if not row:
        row = Secret(key="netease_cookie", value=enc)
        session.add(row)
    else:
        row.value = enc
    session.commit()
    return {"ok": True}
