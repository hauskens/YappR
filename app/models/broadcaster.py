from sqlalchemy import String, Integer, Boolean, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from .channel import Channels

class Broadcaster(Base):
    __tablename__: str = "broadcaster"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)
    channels: Mapped[list["Channels"]] = relationship(
        back_populates="broadcaster", cascade="all, delete-orphan"
    )
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped["BroadcasterSettings"] = relationship(
        back_populates="broadcaster", uselist=False)
    content_queue: Mapped[list["ContentQueue"]] = relationship(
        back_populates="broadcaster", cascade="all, delete-orphan"
    )
    content_queue_settings: Mapped["ContentQueueSettings"] = relationship(
        "ContentQueueSettings", back_populates="broadcaster", uselist=False
    )

#     def delete(self):
#         for channel in self.channels:
#             channel.delete()
#         db.session.query(Users).filter_by(
#             broadcaster_id=self.id).update({"broadcaster_id": None})
#         db.session.flush()
#         db.session.query(BroadcasterSettings).filter_by(
#             broadcaster_id=self.id).delete()
#         db.session.flush()
#         db.session.query(Broadcaster).filter_by(id=self.id).delete()
#         db.session.commit()

#     def last_active(self) -> datetime | None:
#         return db.session.query(func.max(Channels.last_active)).filter_by(broadcaster_id=self.id).scalar()

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