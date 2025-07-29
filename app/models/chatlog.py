from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from .channel import Channels
from datetime import datetime


class ChatLog(Base):
    __tablename__: str = "chatlogs"
    __table_args__ = (
        Index("ix_chatlogs_channel_timestamp", "channel_id", "timestamp"),
    )
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()  # type: ignore[name-defined]
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    username: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(String(600), nullable=False)
    external_user_account_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    imported: Mapped[bool] = mapped_column(Boolean, nullable=False)
