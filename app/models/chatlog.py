from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from .channel import Channels
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import Users

class ChatLogImport(Base):
    __tablename__: str = "chatlog_imports"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    chatlogs: Mapped[list["ChatLog"]] = relationship("ChatLog", back_populates="import_event")
    imported_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    imported_by_user: Mapped["Users"] = relationship()
    timezone: Mapped[str] = mapped_column(String(256), nullable=False)

class ChatLog(Base):
    __tablename__: str = "chatlogs"
    __table_args__ = (
        Index("ix_chatlogs_channel_timestamp", "channel_id", "timestamp"),
    )
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    username: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(String(600), nullable=False)
    external_user_account_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    import_id: Mapped[int | None] = mapped_column(ForeignKey("chatlog_imports.id"), nullable=True, default=None, server_default=None)
    import_event: Mapped["ChatLogImport"] = relationship("ChatLogImport", back_populates="chatlogs")
