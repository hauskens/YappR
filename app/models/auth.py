from sqlalchemy import String, ForeignKey, Integer, Enum, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin  # type: ignore
from .user import Users
from .enums import PermissionType
from datetime import datetime


class OAuth(OAuthConsumerMixin, Base):
    provider_user_id: Mapped[str] = mapped_column(
        String(256), unique=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship()


class Permissions(Base):
    __tablename__: str = "permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship()
    permission_type: Mapped[PermissionType] = mapped_column(
        Enum(PermissionType), default=PermissionType.Reader
    )
    date_added: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now())
