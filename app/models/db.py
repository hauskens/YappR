import enum
from typing import Iterable
from sqlalchemy import (
    Boolean,
    ForeignKey,
    String,
    Integer,
    Enum,
    Float,
    DateTime,
    Text,
    Computed,
    Index,
    UniqueConstraint,
    BigInteger,
)
from sqlalchemy import select, func
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin # type: ignore
from flask_login import UserMixin # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy_utils.types.ts_vector import TSVectorType # type: ignore
from sqlalchemy_file import FileField, File
from datetime import datetime, timedelta
from twitchAPI.twitch import ChannelModerator as TwitchChannelModerator
from app.cache import cache
from io import BytesIO
import webvtt # type: ignore
import re
import asyncio
import json
from app.logger import logger
from typing import Literal
from app.shared import convert_to_srt

from .transcription import TranscriptionResult
from .config import config
from ..utils import (
    get_sec,
    save_yt_thumbnail,
    save_twitch_thumbnail,
    seconds_to_string,
)
from ..youtube_api import (
    get_youtube_channel_details,
    get_videos_on_channel,
    get_all_videos_on_channel,
    get_videos,
    fetch_transcription,
)
from ..tasks import get_twitch_audio, get_yt_audio
from ..twitch_api import get_twitch_user, get_twitch_user_by_id, get_latest_broadcasts, get_twitch_video_by_ids, parse_time, get_moderated_channels

from .youtube.search import SearchResultItem
from youtube_transcript_api.formatters import WebVTTFormatter
from . import db
from .base import Base
from app.platforms.handler import PlatformRegistry


class Broadcaster(Base):
    __tablename__: str = "broadcaster"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)
    channels: Mapped[list["Channels"]] = relationship(
        back_populates="broadcaster", cascade="all, delete-orphan"
    )
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped["BroadcasterSettings"] = relationship(back_populates="broadcaster", uselist=False)
    content_queue: Mapped[list["ContentQueue"]] = relationship(
        back_populates="broadcaster", cascade="all, delete-orphan"
    )
    content_queue_settings: Mapped["ContentQueueSettings"] = relationship(
        "ContentQueueSettings", back_populates="broadcaster", uselist=False
    )
    def delete(self):
        for channel in self.channels:
            channel.delete()
        db.session.query(Users).filter_by(broadcaster_id=self.id).update({"broadcaster_id": None})
        db.session.flush()
        db.session.query(BroadcasterSettings).filter_by(broadcaster_id=self.id).delete()
        db.session.flush()
        db.session.query(Broadcaster).filter_by(id=self.id).delete()
        db.session.commit()

    def last_active(self) -> datetime | None:
        return db.session.query(func.max(Channels.last_active)).filter_by(broadcaster_id=self.id).scalar()
        
        

class BroadcasterSettings(Base):
    __tablename__: str = "broadcaster_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    linked_discord_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    linked_discord_channel_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_discord_disable_voting: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_discord_threads_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    

class Platforms(Base):
    __tablename__: str = "platforms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    color: Mapped[str | None] = mapped_column(
        String(10), nullable=True, default="#FF0000"
    )


class VideoType(enum.Enum):
    Unknown = "unknown"
    VOD = "vod"
    Clip = "clip"
    Edit = "edit"


class TranscriptionSource(enum.Enum):
    Unknown = "unknown"
    YouTube = "youtube"


class PermissionType(enum.Enum):
    Admin = "admin"
    Moderator = "mod"
    Reader = "reader"


class AccountSource(enum.Enum):
    Discord = "discord"
    Twitch = "twitch"


class Users(Base, UserMixin):
    __tablename__: str = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    external_account_id: Mapped[str | None] = mapped_column(
        String(500), unique=True, nullable=True
    )
    account_type: Mapped[str] = mapped_column(Enum(AccountSource))
    first_login: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    last_login: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    broadcaster_id: Mapped[int | None] = mapped_column(ForeignKey("broadcaster.id"))
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions: Mapped[list["Permissions"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    channel_moderators: Mapped[list["ChannelModerator"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    oauth: Mapped[list["OAuth"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def has_permission(
        self, permissions: PermissionType | str | Iterable[PermissionType | str]
    ) -> bool:
        if isinstance(permissions, (PermissionType, str)):
            permissions = [permissions]

        permission_types: list[PermissionType] = [
            PermissionType(perm) if isinstance(perm, str) else perm
            for perm in permissions
        ]

        if self.banned_reason is None:
            return any(p.permission_type in permission_types for p in self.permissions)
        return False

    def has_broadcaster_id(self, broadcaster_id: int) -> bool:
        return db.session.execute(
            select(Broadcaster)
            .join(Broadcaster.channels)
            .where(Channels.platform_channel_id == self.external_account_id, Broadcaster.id == broadcaster_id)
            .limit(1)
        ).scalars().one_or_none() is not None

    def is_moderator(self, broadcaster_id: int|None = None) -> bool:
        if broadcaster_id is None:
            return db.session.query(ChannelModerator).filter_by(user_id=self.id).one_or_none() is not None
        else:
            return db.session.query(ChannelModerator).filter_by(user_id=self.id, channel_id=broadcaster_id).one_or_none() is not None

    def is_broadcaster(self) -> bool:
        return db.session.execute(
            select(Broadcaster)
            .join(Broadcaster.channels)
            .where(Channels.platform_channel_id == self.external_account_id)
            .limit(1)
        ).scalars().one_or_none() is not None

    def get_broadcaster(self) -> Broadcaster | None:
        return db.session.execute(
            select(Broadcaster)
            .join(Broadcaster.channels)
            .where(Channels.platform_channel_id == self.external_account_id)
            .limit(1)
        ).scalars().one_or_none()

    def add_permissions(self, permission_type: PermissionType):
        if not self.has_permission(permission_type):
            db.session.add(
                Permissions(user_id=self.id, permission_type=permission_type)
            )
            db.session.commit()
            logger.info(f"Granted {permission_type.name} to {self.name}!")

    def update_moderated_channels(self) -> list[TwitchChannelModerator]:
        if self.account_type == AccountSource.Twitch:
            try:
                oauth = db.session.query(OAuth).filter_by(user_id=self.id).one_or_none()
                if oauth is None:
                    return []
                moderated_channels = asyncio.run(get_moderated_channels(self.external_account_id, user_token=oauth.token["access_token"], refresh_token=oauth.token["refresh_token"]))
                if moderated_channels is None:
                    return []
                
                logger.info(f"Updating moderated channels for {self.name}")
                
                # Get existing channel moderator entries for this user
                existing_moderators = db.session.query(ChannelModerator).filter_by(user_id=self.id).all()
                existing_moderator_channel_ids = set()
                found_channel_ids = set()
                
                # Process channels from Twitch API
                for channel in moderated_channels:
                    logger.info(f"Updating channel {channel.broadcaster_id} - {channel.broadcaster_name}")
                    existing_channel = db.session.query(Channels).filter_by(platform_channel_id=channel.broadcaster_id).one_or_none()
                    
                    if existing_channel is not None:
                        found_channel_ids.add(existing_channel.id)
                        # Check if this moderator relationship already exists
                        existing_mod = db.session.query(ChannelModerator).filter_by(
                            user_id=self.id, 
                            channel_id=existing_channel.id
                        ).one_or_none()
                        
                        if existing_mod is None:
                            # Add new moderator relationship
                            db.session.add(
                                ChannelModerator(user_id=self.id, channel_id=existing_channel.id)
                            )
                
                # Get all existing channel IDs for this user's moderator entries
                for mod in existing_moderators:
                    existing_moderator_channel_ids.add(mod.channel_id)
                
                # Delete moderator entries that weren't found in the Twitch API response
                channels_to_remove = existing_moderator_channel_ids - found_channel_ids
                if channels_to_remove:
                    logger.info(f"Removing {len(channels_to_remove)} channel moderator entries for {self.name}")
                    
                    db.session.query(ChannelModerator).filter(
                        ChannelModerator.user_id == self.id,
                        ChannelModerator.channel_id.in_(channels_to_remove)
                    ).delete(synchronize_session=False)
                
                db.session.commit()
                return [channel for channel in moderated_channels]
            except Exception as e:
                logger.error(f"Failed to update moderated channels for {self.name}: {e}")
                return []
        else:
            return []

    def get_twitch_account_type(self) -> Literal["partner", "affiliate", "regular"]:
        if self.account_type == AccountSource.Twitch:
            if config.debug == True and config.debug_broadcaster_id is not None and self.external_account_id == str(config.debug_broadcaster_id):
                return "partner"
            user = asyncio.run(get_twitch_user_by_id(self.external_account_id))
            logger.info(user.broadcaster_type)
            if user.id == self.external_account_id:
                return user.broadcaster_type
        return "regular"
    
        
class ChannelModerator(Base):
    __tablename__: str = "channel_moderators"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship(back_populates="channel_moderators")
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship(back_populates="moderators")
    

class Permissions(Base):
    __tablename__: str = "permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship()
    permission_type: Mapped[PermissionType] = mapped_column(
        Enum(PermissionType), default=PermissionType.Reader
    )
    date_added: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())


class Channels(Base):
    __tablename__: str = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250))
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    platform: Mapped["Platforms"] = relationship()
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    platform_channel_id: Mapped[str | None] = mapped_column(
        String(), unique=True, nullable=True
    )
    source_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"), index=True, nullable=True
    )
    source_channel: Mapped["Channels"] = relationship()
    main_video_type: Mapped[str] = mapped_column(
        Enum(VideoType), default=VideoType.Unknown
    )
    videos: Mapped[list["Video"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    settings: Mapped["ChannelSettings"] = relationship(back_populates="channel", uselist=False)
    moderators: Mapped[list["ChannelModerator"]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan"
    )
    last_active: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


    def update_thumbnail(self):
        for video in self.videos:
            if video.thumbnail is None:
                video.fetch_details(force=True)

    def get_url(self) -> str:
        url = self.platform.url
        if self.platform.name.lower() == "youtube":
            return f"{url}/@{self.platform_ref}"
        elif self.platform.name.lower() == "twitch":
            return f"{url}/{self.platform_ref}"
        raise ValueError(f"Could not generate url for channel: {self.id}")

    def update(self):
        if self.platform.name.lower() == "youtube":
            result = get_youtube_channel_details(self.platform_ref)
            self.platform_channel_id = result.id
        elif self.platform.name.lower() == "twitch":
            result = asyncio.run(get_twitch_user(self.platform_ref))
            self.platform_channel_id = result.id
        db.session.commit()

    def link_to_channel(self, channel_id: int | None = None):
        if channel_id is not None:
            try:
                target_channel = (
                    db.session.query(Channels)
                    .filter_by(id=channel_id, broadcaster_id=self.broadcaster_id)
                    .one()
                )
                self.source_channel_id = (
                    target_channel.id
                )  # I could have just taken channel_id directly from function, but this is to validate that it exists on broadcaster
                db.session.commit()
            except:
                raise ValueError(
                    "Failed to find target channel on broadcaster, is the broadcaster the same?"
                )
        else:
            self.source_channel_id = None
            db.session.commit()

    def delete(self):
        for video in self.videos:
            video.delete()
        db.session.query(ChatLog).filter_by(channel_id=self.id).delete()
        db.session.query(ChannelSettings).filter_by(channel_id=self.id).delete()
        db.session.query(ChannelModerator).filter_by(channel_id=self.id).delete()
        if self.broadcaster_id is not None:
            queue = db.session.query(ContentQueue).filter_by(broadcaster_id=self.broadcaster_id).all()
            for q_item in queue:
                db.session.query(ContentQueueSubmission).filter_by(content_queue_id=q_item.id).delete()
            db.session.query(ContentQueue).filter_by(broadcaster_id=self.broadcaster_id).delete()

        _ = db.session.query(Channels).filter_by(id=self.id).delete()
        db.session.commit()

    def process_videos(self, force: bool = False):
        for video in self.videos:
            video.process_transcriptions(force)

    def download_audio_videos(self, force: bool = False):
        for video in self.videos:
            video.save_audio(force)

    def get_videos_sorted_by_uploaded(self, descending: bool = True) -> list["Video"]:
        return sorted(self.videos, key=lambda v: v.uploaded, reverse=descending)
    
    def get_videos_sorted_by_id(self, descending: bool = True) -> list["Video"]:
        return sorted(self.videos, key=lambda v: v.id, reverse=descending)

    def look_for_linked_videos(self, margin_sec: int = 2, min_duration: int = 300):
        logger.info(f"Looking for potential links on channel {self.name}")
        for source_video in self.source_channel.videos:
            for target_video in self.videos:
                if (
                    target_video.source_video_id is None
                    and target_video.duration > min_duration
                    and (
                        (source_video.duration - margin_sec)
                        <= target_video.duration
                        <= (source_video.duration + margin_sec)
                    )
                ):
                    logger.info(
                        f"Found a match on video duration! Source: {source_video.id} -> target: {target_video.id}"
                    )
                    target_video.source_video_id = source_video.id
                    db.session.flush()
        db.session.commit()

    def fetch_videos_all(self):
        if self.platform.name.lower() != "youtube":
            return

        latest_video_batches = get_all_videos_on_channel(self.platform_channel_id)

        video_id_set = set()
        for item in latest_video_batches:
            video_id = item.id.videoId
            logger.info(f"Checking for existing video ref: {video_id}")
            existing_video = (
                db.session.query(Video)
                .filter_by(platform_ref=video_id)
                .one_or_none()
            )
            if existing_video is None:
                logger.info(f"New video found: {video_id}")
                video_id_set.add(video_id)
        if not video_id_set:
            logger.info("No new videos found.")
            return

        video_details = get_videos(list(video_id_set))

        for video in video_details:
            try:
                tn = save_yt_thumbnail(video, force=True)
                db.session.add(
                    Video(
                        title=video.snippet.title,
                        video_type=VideoType.VOD,
                        channel_id=self.id,
                        platform_ref=video.id,
                        duration=video.contentDetails.duration.total_seconds(),
                        uploaded=video.snippet.publishedAt,
                        thumbnail=open(tn, "rb"),
                    )
                )
            except Exception as e:
                logger.error(f"Failed to add video {video.id}, exception: {e}")
                continue
            db.session.flush()

        db.session.commit()

    def fetch_latest_videos(self, process: bool = False) -> int | None:
        if (
            self.platform.name.lower() == "youtube" and self.platform_channel_id is not None
        ):
            latest_videos = get_videos_on_channel(self.platform_channel_id)
            videos_result: list[SearchResultItem] = []
            for search_result in latest_videos.items:
                existing_video = (
                    db.session.query(Video)
                    .filter_by(platform_ref=search_result.id.videoId)
                    .one_or_none()
                )
                if existing_video is None:
                    videos_result.append(search_result)

            videos_details = get_videos([item.id.videoId for item in videos_result])
            for video in videos_details:
                tn = save_yt_thumbnail(video, force=True)
                db.session.add(
                    Video(
                        title=video.snippet.title,
                        video_type=VideoType.VOD,
                        channel_id=self.id,
                        platform_ref=video.id,
                        duration=video.contentDetails.duration.total_seconds(),
                        uploaded=video.snippet.publishedAt,
                        thumbnail=open(tn, "rb"),
                    )
                )
            db.session.commit()
        elif (
            self.platform.name.lower() == "twitch" and self.platform_channel_id is not None
        ):
            logger.info(f"Fetching latest videos for twitch channel: {self.name} - Process: {process}")
            limit = 1 if process else 100
            twitch_latest_videos = asyncio.run(
                get_latest_broadcasts(self.platform_channel_id, limit=limit)
            )
            for video_data in twitch_latest_videos:
                logger.info(f"Processing video ref: {video_data.id} - got {len(twitch_latest_videos)} videos")
                
                # Query full DB, not just self.videos
                existing_video = (
                    db.session.query(Video)
                    .filter_by(platform_ref=video_data.id)
                    .one_or_none()
                )


                if existing_video is None:
                    tn = save_twitch_thumbnail(video_data, force=True)
                    logger.info(f"Found new video ref: {video_data.id}")
                    vid = Video(
                        title=video_data.title,
                        video_type=VideoType.VOD,
                        channel_id=self.id,
                        platform_ref=video_data.id,
                        duration=parse_time(video_data.duration),
                        uploaded=video_data.created_at,
                        thumbnail=open(tn, "rb"),
                        active=True,
                    )
                    db.session.add(vid)
                    if process:
                        db.session.commit()
                        return db.session.query(Video).filter_by(platform_ref=video_data.id).one().id
                else:
                    try:
                        tn = save_twitch_thumbnail(video_data, force=True)
                        logger.info(f"Updating existing video: {video_data.id}")
                        existing_video.thumbnail = open(tn, "rb") # type: ignore
                        existing_video.active = True
                        existing_video.title = video_data.title
                        existing_video.uploaded = video_data.created_at
                        db.session.flush()
                        if abs(existing_video.duration - parse_time(video_data.duration)) > 1:
                            logger.info(
                                f"Duration changed for video {self.platform_ref}: {existing_video.duration} -> {parse_time(video_data.duration)}"
                            )
                            for transcription in existing_video.transcriptions:
                                transcription.delete()
                            try:
                                if existing_video.audio is not None:
                                    existing_video.audio.file.object.delete()
                            except Exception as e:
                                logger.error(f"Failed to delete audio for video {self.platform_ref}, exception: {e}")
                            existing_video.audio = None
                            existing_video.duration = parse_time(video_data.duration)
                        if process:
                            return existing_video.id
                        if existing_video.channel_id != self.id:
                            existing_video.channel_id = self.id
                        db.session.flush()
                    except Exception as e:
                        logger.error(f"Failed to update video {video_data.id}, exception: {e}")
                        continue
        db.session.commit()
        return None

class ChannelSettings(Base):
    __tablename__ = "channel_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), unique=True)
    content_queue_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    chat_collection_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    channel: Mapped["Channels"] = relationship(back_populates="settings")

class Video(Base):
    __tablename__: str = "video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    video_type: Mapped[VideoType] = mapped_column(Enum(VideoType))
    duration: Mapped[float] = mapped_column(Float())
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    channel: Mapped["Channels"] = relationship()
    source_video_id: Mapped[int | None] = mapped_column(
        ForeignKey("video.id"), index=True, nullable=True
    )
    source_video: Mapped["Video"] = relationship(
        back_populates="video_refs", remote_side="Video.id"
    )
    video_refs: Mapped[list["Video"]] = relationship(back_populates="source_video")
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    uploaded: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime(1970, 1, 1)
    )
    platform_ref: Mapped[str] = mapped_column(String(), unique=True)
    active: Mapped[bool] = mapped_column(Boolean(), default=True)
    thumbnail: Mapped[File | None] = mapped_column(FileField(upload_storage="thumbnails"))
    audio: Mapped[File | None] = mapped_column(FileField())
    transcriptions: Mapped[list["Transcription"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )

    def get_date_str(self) -> str:
        return f"{self.uploaded.strftime("%d.%m.%Y")}"

    def delete(self):
        for t in self.transcriptions:
            t.delete()
        _ = db.session.query(Video).filter_by(id=self.id).delete()
        db.session.commit()

    def get_duration_str(self) -> str:
        return seconds_to_string(self.duration)

    def get_url(self) -> str:
        url = self.channel.platform.url
        if self.channel.platform.name.lower() == "youtube":
            return f"{url}/watch?v={self.platform_ref}"
        elif self.channel.platform.name.lower() == "twitch":
            return f"{url}/videos/{self.platform_ref}"
        raise ValueError(f"Could not generate url for video: {self.id}")
        
    def get_url_with_timestamp(self, seconds_offset: float) -> str:
        """Generate a URL to the video at a specific timestamp.
        
        Args:
            seconds_offset: Number of seconds from the start of the video
            
        Returns:
            URL string with appropriate timestamp format for the platform
        """
        base_url = self.get_url()
        
        # Ensure seconds_offset is positive and within video duration
        seconds_offset = max(0, min(seconds_offset, self.duration))
        
        # Format timestamp based on platform
        if self.channel.platform.name.lower() == "youtube":
            # YouTube uses t=123s format (seconds)
            return f"{base_url}&t={int(seconds_offset)}s"
        elif self.channel.platform.name.lower() == "twitch":
            # Twitch uses t=01h23m45s format
            hours = int(seconds_offset // 3600)
            minutes = int((seconds_offset % 3600) // 60)
            seconds = int(seconds_offset % 60)
            
            if hours > 0:
                timestamp = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"
            else:
                timestamp = f"{minutes:02d}m{seconds:02d}s"
                
            return f"{base_url}?t={timestamp}"
        
        # Default fallback
        return base_url

    def archive(self):
        for video in self.video_refs:
            if video.video_type == VideoType.VOD:
                for transcription in self.transcriptions:
                    transcription.video_id = video.id
                    logger.info(
                        f"Transcription id: {transcription.id} on video id{self.id} is transfered to {video.id}"
                    )
                db.session.commit()

    def fetch_details(self, force: bool = True):
        if self.channel.platform.name.lower() == "youtube":
            try:
                result = get_videos([self.platform_ref])[0]
            except Exception as e:
                res = get_videos([self.platform_ref])
                logger.error(f"Failed to fetch details for video {self.id}: {e} - {res}")
                return
            self.duration = result.contentDetails.duration.total_seconds()
            self.title = result.snippet.title
            self.uploaded = result.snippet.publishedAt
            tn = save_yt_thumbnail(result)
            self.thumbnail = open(tn, "rb") # type: ignore
            db.session.commit()
        if self.channel.platform.name.lower() == "twitch":
            try:
                twitch_result = asyncio.run(get_twitch_video_by_ids([self.platform_ref]))[0]
            except Exception as e:
                logger.error(f"Failed to fetch details for video {self.id}: {e}")
                return
            if self.duration != parse_time(twitch_result.duration):
                logger.info(
                    f"Duration changed for video {self.platform_ref}: {self.duration} -> {parse_time(twitch_result.duration)}"
                )
                for transcription in self.transcriptions:
                    transcription.delete()
                try:
                    if self.audio is not None:
                        self.audio.file.object.delete()
                except Exception as e:
                    logger.error(f"Failed to delete audio for video {self.platform_ref}, exception: {e}")
                self.audio = None
                self.duration = parse_time(twitch_result.duration)
            self.title = twitch_result.title
            self.uploaded = twitch_result.created_at
            # if self.thumbnail is None or force:
            tn = save_twitch_thumbnail(twitch_result)
            self.thumbnail = open(tn, "rb") # type: ignore
            db.session.commit()

    def download_transcription(self, force: bool = False):
        if force:
            for t in self.transcriptions:
                if t.source == TranscriptionSource.YouTube:
                    logger.info(
                        f"transcriptions found {self.platform_ref}, forcing delete"
                    )
                    db.session.delete(t)
            db.session.commit()
        if len(self.transcriptions) == 0:
            logger.info(
                f"transcriptions not found on {self.platform_ref}, adding new.."
            )
            formatter = WebVTTFormatter()
            path = config.cache_location + self.platform_ref + ".vtt"
            transcription = fetch_transcription(self.platform_ref)
            t_formatted = formatter.format_transcript(transcription)
            with open(path, "w", encoding="utf-8") as vtt_file:
                _ = vtt_file.write(t_formatted)
            db.session.add(
                Transcription(
                    video_id=self.id,
                    language=transcription.language,
                    file_extention="vtt",
                    file=open(path, "rb"),
                    source=TranscriptionSource.YouTube,
                )
            )
            db.session.commit()

    def process_transcriptions(self, force: bool = False):
        transcription_to_process: Transcription | None = None
        for t in self.transcriptions:
            if force:
                t.reset()
            if len(self.transcriptions) == 1:
                transcription_to_process = t
            if (
                len(self.transcriptions) > 1
                and t.source is not TranscriptionSource.YouTube
            ):
                transcription_to_process = t
            if len(self.transcriptions) > 1 and t.source is TranscriptionSource.YouTube:
                t.reset()

        logger.info(
            f"Processing transcriptions for {self.id}, found {transcription_to_process}"
        )
        if transcription_to_process is not None:
            transcription_to_process.reset()
            transcription_to_process.process_transcription(force)

    def save_audio(self, force: bool = False):
        if (
            self.channel.platform.name.lower() == "twitch"
        ):
            audio = get_twitch_audio(self.get_url())
            self.audio = open(audio, "rb") # type: ignore
            db.session.commit()
        if (
            self.channel.platform.name.lower() == "youtube"
        ):
            audio = get_yt_audio(self.get_url())
            self.audio = open(audio, "rb") # type: ignore
            db.session.commit()


class Transcription(Base):
    __tablename__: str = "transcriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), index=True)
    video: Mapped["Video"] = relationship()
    language: Mapped[str] = mapped_column(String(250))
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    file_extention: Mapped[str] = mapped_column(String(10))
    file: Mapped[File] = mapped_column(FileField())
    source: Mapped[TranscriptionSource] = mapped_column(
        Enum(TranscriptionSource), default=TranscriptionSource.Unknown
    )
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    segments: Mapped[list["Segments"]] = relationship(
        back_populates="transcription", cascade="all, delete-orphan"
    )

    def delete(self):
        self.reset()
        _ = db.session.query(Transcription).filter_by(id=self.id).delete()
        db.session.commit()

    def reset(self):
        self.delete_attached_segments()
        self.processed = False

    def delete_attached_segments(self):
        _ = db.session.query(Segments).filter_by(transcription_id=self.id).delete()
        self.processed = False
        db.session.commit()

    def get_segments_sorted(self, descending: bool = True) -> list["Segments"]:
        return sorted(self.segments, key=lambda v: v.start, reverse=not descending)

    def process_transcription(self, force: bool = False):
        logger.info(f"Task queued, parsing transcription for {self.id}, - {force}")
        if self.processed and force == False and len(self.segments) == 0:
            logger.info(f"Transcription {self.id}, already processed.. skipping")
            return
        if force:
            self.reset()
        if self.file_extention == "vtt":
            _ = self.parse_vtt()
        elif self.file_extention == "json":
            _ = self.parse_json()
        self.processed = True
        db.session.commit()
        
    def to_srt(self) -> str:
        """
        Convert the transcription to SRT format.
        
        Returns:
            str: The transcription in SRT format
        """
        if not self.processed:
            self.process_transcription()
            
        segments = self.get_segments_sorted()
        srt_content = convert_to_srt(segments)
        return srt_content
    
    def to_json(self) -> str:
        """
        Convert the transcription to JSON format.
        
        Returns:
            str: The transcription in JSON format
        """
        if not self.processed:
            self.process_transcription()
            
        segments = self.get_segments_sorted()
        json_segments = []
        
        for segment in segments:
            json_segments.append({
                "text": segment.text,
                "start": segment.start,
                "end": segment.end
            })
            
        result = {
            "segments": json_segments,
            "language": self.language
        }
        
        return json.dumps(result, ensure_ascii=False)
    
    def save_as_srt(self, output_path: str | None = None) -> str:
        """
        Convert the transcription to SRT format and save it to a file.
        
        Args:
            output_path: Path to save the SRT file. If None, a path will be generated
                        based on the video ID and transcription ID.
                        
        Returns:
            str: Path to the saved SRT file
        """
        srt_content = self.to_srt()
        
        if output_path is None:
            # Generate a filename based on video ID and transcription ID
            output_path = f"transcription_{self.video_id}_{self.id}.srt"
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
            
        logger.info(f"Saved SRT file to {output_path}")
        return output_path
        
    def save_as_json(self, output_path: str | None = None) -> str:
        """
        Convert the transcription to JSON format and save it to a file.
        
        Args:
            output_path: Path to save the JSON file. If None, a path will be generated
                        based on the video ID and transcription ID.
                        
        Returns:
            str: Path to the saved JSON file
        """
        json_content = self.to_json()
        
        if output_path is None:
            # Generate a filename based on video ID and transcription ID
            output_path = f"transcription_{self.video_id}_{self.id}.json"
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_content)
            
        logger.info(f"Saved JSON file to {output_path}")
        return output_path

    def parse_json(self):
        logger.info(f"Processing json transcription: {self.id}")
        segments: list[Segments] = []
        content = TranscriptionResult.model_validate_json(
            self.file.file.read().decode()
        )
        self.reset()

        previous_segment: Segments | None = None
        logger.info(f"Processing json transcription: {self.id}")
        for caption in content.segments:
            start = int(caption.start)
            if caption.text == "":
                continue
            if previous_segment is not None and caption.text == previous_segment.text:
                continue

            segment = Segments(
                text=caption.text,
                start=start,
                transcription_id=self.id,
                end=int(caption.end),
                previous_segment_id=(
                    previous_segment.id if previous_segment is not None else None
                ),
            )
            db.session.add(segment)
            db.session.flush()
            if previous_segment is not None:
                previous_segment.next_segment_id = segment.id
                db.session.add(previous_segment)
                db.session.flush()

            previous_segment = segment
            segments.append(segment)
        db.session.commit()
        logger.info(f"Done processing transcription: {self.id}")

    def parse_vtt(self):
        logger.info(f"Processing vtt transcription: {self.id}")
        segments: list[Segments] = []
        content = BytesIO(self.file.file.read())
        previous_segment: Segments | None = None
        for caption in webvtt.from_buffer(content):
            start = get_sec(caption.start)
            # remove annotations, such as [music]
            text = re.sub(r"\[.*?\]", "", caption.text).strip().lower()

            if "\n" in text:
                continue
            if text == "":
                continue
            if previous_segment is not None and text == previous_segment.text:
                continue

            segment = Segments(
                text=text,
                start=start,
                transcription_id=self.id,
                end=get_sec(caption.end),
                previous_segment_id=(
                    previous_segment.id if previous_segment is not None else None
                ),
            )
            db.session.add(segment)
            db.session.flush()
            if previous_segment is not None:
                previous_segment.next_segment_id = segment.id
                db.session.add(previous_segment)
                db.session.flush()

            previous_segment = segment
            segments.append(segment)
        db.session.commit()
        logger.info(f"Done processing transcription: {self.id}")


class Segments(Base):
    __tablename__: str = "segments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_tsv: Mapped[TSVectorType] = mapped_column(
        TSVectorType("text", regconfig="simple"),
        Computed("to_tsvector('simple', \"text\")", persisted=True),
        index=True,
    )
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_segment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_segment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcription_id: Mapped[int] = mapped_column(
        ForeignKey("transcriptions.id"), index=True
    )
    transcription: Mapped["Transcription"] = relationship()

    def get_url_timestamped(self, time_shift: int = 5) -> str:
        shifted_time = self.start - time_shift
        if shifted_time < 0:
            shifted_time = 0
        if self.transcription.video.channel.platform.name.lower() == "twitch":
            hours = shifted_time // 3600
            minutes = (shifted_time % 3600) // 60
            seconds = shifted_time % 60
            return f"{self.transcription.video.get_url()}?t={hours:02d}h{minutes:02d}m{seconds:02d}s"

        elif self.transcription.video.channel.platform.name.lower() == "youtube":
            return f"{self.transcription.video.get_url()}&t={shifted_time}"
        raise ValueError("Could not generate url with timestamp")

class ChatLog(Base):
    __tablename__: str = "chatlogs"
    __table_args__ = (
        Index("ix_chatlogs_channel_timestamp", "channel_id", "timestamp"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    username: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(String(600), nullable=False)
    external_user_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    
    
class ChannelEvent(Base):
    __tablename__ = "channel_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    channel: Mapped["Channels"] = relationship()

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_message: Mapped[str] = mapped_column(String(512), nullable=False) 

class OAuth(OAuthConsumerMixin, Base):
    provider_user_id: Mapped[str] = mapped_column(
        String(256), unique=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["Users"] = relationship()

class ExternalUser(Base):
    __tablename__ = "external_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(600), nullable=False)
    external_account_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True
    )
    account_type: Mapped[AccountSource] = mapped_column(Enum(AccountSource))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ignore_weight_penalty: Mapped[bool] = mapped_column(Boolean, default=False)
    submissions: Mapped[list["ContentQueueSubmission"]] = relationship(back_populates="user")
    weights: Mapped[list["ExternalUserWeight"]] = relationship(back_populates="external_user")
    
class ExternalUserWeight(Base):
    __tablename__ = "external_user_weights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_user_id: Mapped[int] = mapped_column(ForeignKey("external_users.id"))
    external_user: Mapped["ExternalUser"] = relationship(back_populates="weights")
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    unban_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Content(Base):
    __tablename__ = "content"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    stripped_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    channel_name: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, server_default=None)

    def get_platform(self):
        return PlatformRegistry.get_handler_by_url(self.url).platform_name

    def get_video_timestamp_url(self, timestamp: int):
        return PlatformRegistry.get_url_with_timestamp(self.url, timestamp)

class ContentQueue(Base):
    __tablename__ = "content_queue"
    __table_args__ = (
        UniqueConstraint("broadcaster_id", "content_id", name="uq_broadcaster_content"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    content_id: Mapped[int] = mapped_column(ForeignKey("content.id"))
    content: Mapped["Content"] = relationship()
    content_timestamp: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=None)
    watched: Mapped[bool] = mapped_column(Boolean, default=False)
    watched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    submissions: Mapped[list["ContentQueueSubmission"]] = relationship(back_populates="content_queue")
    score: Mapped[float] = mapped_column(Float, default=0, server_default='0')
    
    @property
    def total_weight(self) -> float:
        """Calculate the total weight of all related ContentQueueSubmission entries.
        This is a calculated property and not stored in the database.
        
        Returns:
            float: Sum of all submission weights, or 0 if there are no submissions
        """
        if not self.submissions:
            return 0.0
        return sum(submission.weight for submission in self.submissions)
    
    def get_video_timestamp_url(self) -> str:
        if self.content_timestamp is None:
            raise ValueError("No timestamp on content")
        return PlatformRegistry.get_url_with_timestamp(self.content.url, self.content_timestamp)

    def get_video_playable_url(self) -> str:
        if self.content_timestamp is None:
            return self.content.url
        return self.get_video_timestamp_url()

    def get_vod_timestamp_url(self, time_shift: float = 60) -> str | None:
        """Find the broadcaster's video that was live when this clip was marked as watched
        and return a URL with the timestamp.
        
        The function finds the closest previous watched item with the same broadcaster_id
        and uses that time for the timestamp URL. If the time difference between this item
        and the previous one is longer than 90 seconds + video duration, it uses that instead.
        
        Args:
            time_shift: Default time shift in seconds (used as fallback if no previous item found)
            
        Returns:
            URL string with timestamp or None if no matching video found
        """
        if not self.watched or not self.watched_at:
            return None
        
        # Find the closest previous watched item with the same broadcaster_id
        previous_item = db.session.query(ContentQueue).filter(
            ContentQueue.broadcaster_id == self.broadcaster_id,
            ContentQueue.watched == True,
            ContentQueue.watched_at < self.watched_at
        ).order_by(ContentQueue.watched_at.desc()).first()
        # Calculate the time difference to use for the offset
        if previous_item and previous_item.watched_at:
            # Calculate time difference in seconds between current and previous item
            content_duration = self.content.duration or 0
            
            # Subtract content duration from the time difference
            time_diff = (self.watched_at - previous_item.watched_at).total_seconds() 
            
            # Ensure time_diff is at least 0
            time_diff = max(0, time_diff)
            
            # Use the minimum of the actual time difference and 90 seconds
            time_shift = min(time_diff, 90 + content_duration)
            
        # Find videos from this broadcaster's channels that were live when the clip was watched
        for channel in self.broadcaster.channels:
            # Look for videos that might include this timestamp
            # We need to find videos that were live when the clip was watched
            # SQLite doesn't have great datetime functions, so we'll fetch candidates and filter in Python
            candidate_videos = db.session.query(Video).filter(
                Video.channel_id == channel.id,
                Video.video_type == VideoType.VOD  # Ensure it's a VOD
            ).all()
            
            for video in candidate_videos:
                # Check if video was live when clip was watched
                video_end_time = video.uploaded + timedelta(seconds=video.duration)
                if video.uploaded <= self.watched_at <= video_end_time:
                    # Calculate seconds from start of video to when clip was watched
                    seconds_offset = (self.watched_at - video.uploaded - timedelta(seconds=time_shift)).total_seconds()
                    
                    # Generate URL with timestamp
                    return video.get_url_with_timestamp(seconds_offset)
                
        return None
    
class ContentQueueSubmissionSource(enum.Enum):
    Discord = "discord" # Comes from a message in a linked channel based on broadcaster settings
    Twitch = "twitch" # Comes from a clip submission in twitch
    Web = "web" # Comes from a clip submission in web interface

class ContentQueueSubmission(Base):
    __tablename__ = "content_queue_submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_queue_id: Mapped[int] = mapped_column(ForeignKey("content_queue.id"))
    content_queue: Mapped["ContentQueue"] = relationship(back_populates="submissions")
    content_id: Mapped[int] = mapped_column(ForeignKey("content.id"))
    content: Mapped["Content"] = relationship()
    user_id: Mapped[int] = mapped_column(ForeignKey("external_users.id"))
    user: Mapped["ExternalUser"] = relationship()
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    submission_source_type: Mapped[ContentQueueSubmissionSource] = mapped_column(Enum(ContentQueueSubmissionSource), nullable=False)
    submission_source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    user_comment: Mapped[str | None] = mapped_column(String(256), nullable=True)



class ContentQueueSettings(Base):
    __tablename__ = "content_queue_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    prefer_shorter_content: Mapped[bool] = mapped_column(Boolean, default=False)
    view_count_min: Mapped[int] = mapped_column(Integer, default=0)
    allowed_platforms: Mapped[str] = mapped_column(Text, default="")

    @property
    def get_allowed_platforms(self) -> list[str]:
        """Get list of allowed platforms. Empty means all platforms allowed."""
        if not self.allowed_platforms:
            # Get all available platforms from registry
            from app.platforms.handler import PlatformRegistry
            return list(PlatformRegistry._handlers.keys())
        return [p.strip() for p in self.allowed_platforms.split(",") if p.strip()]
    
    def is_platform_allowed(self, platform: str) -> bool:
        """Check if a platform is allowed.
        
        Args:
            platform: Platform name to check
            
        Returns:
            True if platform is allowed or if no platforms are specified (all allowed),
            False otherwise
        """
        if not self.allowed_platforms:
            return True  # All platforms allowed
        return platform in self.get_allowed_platforms
    
    def set_allowed_platforms(self, platforms: list[str]) -> None:
        """Set the allowed platforms list.
        
        Args:
            platforms: List of platform names to allow
            
        Note: 
            Empty list means all platforms are allowed
        """
        self.allowed_platforms = ",".join(platforms) if platforms else ""
    
    