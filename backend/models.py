from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Secret(Base):
    __tablename__ = "secrets"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class QueueItem(Base):
    __tablename__ = "queue_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    track_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(Text)


class HistoryItem(Base):
    __tablename__ = "history_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    played_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    track_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(64), default="")
