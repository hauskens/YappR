from sqlalchemy import String, Integer, Boolean, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pydantic import BaseModel, ConfigDict, Field
from .base import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .channel import Channels
    from .content_queue import ContentQueue
    from .content_queue_settings import ContentQueueSettings

class Broadcaster(Base):
    __tablename__: str = "broadcaster"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)
    channels: Mapped[list["Channels"]] = relationship( # type: ignore[name-defined]
        back_populates="broadcaster", cascade="all, delete-orphan"
    )
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped["BroadcasterSettings"] = relationship(
        back_populates="broadcaster", uselist=False)
    content_queue: Mapped[list["ContentQueue"]] = relationship( # type: ignore[name-defined]
        back_populates="broadcaster", cascade="all, delete-orphan"
    )
    content_queue_settings: Mapped["ContentQueueSettings"] = relationship( # type: ignore[name-defined]
        "ContentQueueSettings", back_populates="broadcaster", uselist=False
    )


class BroadcasterModel(BaseModel):
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)


class BroadcasterSettings(Base):
    __tablename__: str = "broadcaster_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    linked_discord_channel_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True)
    linked_discord_channel_verified: Mapped[bool] = mapped_column(
        Boolean, default=False)
    linked_discord_disable_voting: Mapped[bool] = mapped_column(
        Boolean, default=False)
    linked_discord_threads_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")


if __name__ == "__main__":
    print("test")
