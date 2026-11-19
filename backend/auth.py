from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import os
from pathlib import Path
import secrets

from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .logger import logger
from .models import AdminCredential, AdminSession


SESSION_COOKIE = settings.session_cookie_name
SESSION_DAYS = 7
PBKDF2_ITERATIONS = 600_000


def _now() -> datetime:
    return datetime.now()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(actual, bytes.fromhex(digest_hex))
    except (TypeError, ValueError):
        return False


def _initial_password_file() -> Path:
    configured = (settings.initial_password_file or "").strip()
    path = Path(configured or "./logs/initial-admin-password.txt")
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def initialize_admin(session: Session) -> str | None:
    credential = session.get(AdminCredential, 1)
    if credential is not None:
        return None

    initial_password = (
        (settings.initial_admin_password or "").strip()
        or (settings.admin_token or "").strip()
        or secrets.token_urlsafe(18)
    )
    credential = AdminCredential(
        id=1,
        username="admin",
        password_hash=hash_password(initial_password),
        must_change_password=True,
        password_version=1,
    )
    session.add(credential)
    session.commit()

    password_file = _initial_password_file()
    try:
        password_file.parent.mkdir(parents=True, exist_ok=True)
        password_file.write_text(initial_password + "\n", encoding="utf-8")
        os.chmod(password_file, 0o600)
        file_note = f"，同时写入 {password_file}"
    except OSError as exc:
        logger.warning("无法写入初始管理员密码文件 %s: %s", password_file, exc)
        file_note = ""
    logger.warning("首次启动管理员账号：admin，初始密码：%s%s；首次登录后必须修改", initial_password, file_note)
    return initial_password


def remove_initial_password_file() -> None:
    try:
        _initial_password_file().unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("无法删除初始管理员密码文件: %s", exc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(session: Session, credential: AdminCredential) -> tuple[str, AdminSession]:
    raw_token = secrets.token_urlsafe(32)
    row = AdminSession(
        token_hash=_token_hash(raw_token),
        csrf_token=secrets.token_urlsafe(24),
        password_version=credential.password_version,
        expires_at=_now() + timedelta(days=SESSION_DAYS),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return raw_token, row


def set_session_cookie(response: Response, raw_token: str, request: Request) -> None:
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    secure = request.url.scheme == "https" or forwarded == "https"
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")


def get_admin_session(request: Request, session: Session) -> tuple[AdminCredential, AdminSession]:
    raw_token = request.cookies.get(SESSION_COOKIE, "")
    if not raw_token:
        raise HTTPException(status_code=401, detail="请先登录管理员账号")
    row = session.scalar(select(AdminSession).where(AdminSession.token_hash == _token_hash(raw_token)))
    credential = session.get(AdminCredential, 1)
    if (
        row is None
        or credential is None
        or row.expires_at <= _now()
        or row.password_version != credential.password_version
    ):
        if row is not None:
            session.delete(row)
            session.commit()
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return credential, row


def require_admin(request: Request, session: Session, *, allow_password_change: bool = False) -> tuple[AdminCredential, AdminSession]:
    credential, admin_session = get_admin_session(request, session)
    if credential.must_change_password and not allow_password_change:
        raise HTTPException(status_code=403, detail="首次登录必须先修改密码")
    return credential, admin_session


def require_csrf(request: Request, admin_session: AdminSession) -> None:
    provided = request.headers.get("x-csrf-token", "")
    if not provided or not hmac.compare_digest(provided, admin_session.csrf_token):
        raise HTTPException(status_code=403, detail="无效的 CSRF 令牌")


def invalidate_sessions(session: Session) -> None:
    session.execute(delete(AdminSession))
    session.commit()
