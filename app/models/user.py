from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, Text, Enum, Float, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .base import Base
from .enums import AccountSource
from flask_login import UserMixin  # type: ignore
from pydantic import BaseModel


class Users(Base, UserMixin):
    __tablename__: str = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    external_account_id: Mapped[str] = mapped_column(
        String(500), unique=True, nullable=False
    )
    account_type: Mapped[str] = mapped_column(Enum(AccountSource))
    first_login: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now())
    last_login: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now())
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    broadcaster_id: Mapped[int | None] = mapped_column(
        ForeignKey("broadcaster.id"))
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions: Mapped[list["Permissions"]] = relationship(  # type: ignore[name-defined]
        back_populates="user", cascade="all, delete-orphan"
    )
    channel_moderators: Mapped[list["ChannelModerator"]] = relationship(  # type: ignore[name-defined]
        back_populates="user", cascade="all, delete-orphan"
    )
    oauth: Mapped[list["OAuth"]] = relationship(  # type: ignore[name-defined]
        back_populates="user", cascade="all, delete-orphan"
    )



class ExternalUser(Base):
    __tablename__ = "external_users"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(600), nullable=False)
    external_account_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True
    )
    account_type: Mapped[AccountSource] = mapped_column(Enum(AccountSource))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ignore_weight_penalty: Mapped[bool] = mapped_column(Boolean, default=False)
    submissions: Mapped[list["ContentQueueSubmission"]  # type: ignore[name-defined]
                        ] = relationship(back_populates="user")
    weights: Mapped[list["ExternalUserWeight"]] = relationship(
        back_populates="external_user")


class ExternalUserWeight(Base):
    __tablename__ = "external_user_weights"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    external_user_id: Mapped[int] = mapped_column(
        ForeignKey("external_users.id"))
    external_user: Mapped["ExternalUser"] = relationship(
        back_populates="weights")
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship() # type: ignore[name-defined]
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    unban_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
