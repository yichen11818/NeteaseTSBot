from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")

    likes: Mapped[list["Like"]] = relationship("Like", back_populates="user", cascade="all, delete-orphan")


class Secret(Base):
    __tablename__ = "secrets"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class UserSecret(Base):
    __tablename__ = "user_secrets"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_secret"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(Text)


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "track_id", name="uq_like_user_track"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    track_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(255), default="")

    user: Mapped[User] = relationship(back_populates="likes")


class QueueItem(Base):
    __tablename__ = "queue_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    track_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(Text)

    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class HistoryItem(Base):
    __tablename__ = "history_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    played_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    track_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(64), default="")
