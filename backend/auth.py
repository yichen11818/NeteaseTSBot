from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .db import get_session
from .models import User

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_token_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_token_scheme),
    session: Session = Depends(get_session),
) -> User:
    if settings.disable_auth:
        user = session.get(User, 1)
        if user:
            return user
        admin = session.query(User).filter(User.username == settings.admin_username).one_or_none()
        if admin:
            return admin
        raise HTTPException(status_code=401, detail="no admin user")

    if credentials is None:
        raise HTTPException(status_code=401, detail="missing token")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="invalid token")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="invalid token")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if settings.disable_auth:
        return user
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin required")
    return user
