from enum import Enum


class VideoType(Enum):
    Unknown = "unknown"
    VOD = "vod"
    Clip = "clip"  # Represents a clip on a platform such as twitch clips, youtube shorts etc
    Edit = "edit"  # Represents a edited video, such as a montage, collection of clips or other edited content


class PlatformType(Enum):
    YouTube = "youtube"
    Twitch = "twitch"


class TranscriptionSource(Enum):
    Unknown = "unknown"
    YouTube = "youtube"


class PermissionType(Enum):
    Admin = "admin"
    Moderator = "mod"
    Reader = "reader"


class AccountSource(Enum):
    Discord = "discord"
    Twitch = "twitch"


class ContentQueueSubmissionSource(Enum):
    # Comes from a message in a linked channel based on broadcaster settings
    Discord = "discord"
    Twitch = "twitch"  # Comes from a clip submission in twitch
    Web = "web"  # Comes from a clip submission in web interface


class TwitchAccountType(Enum):
    Partner = "partner"
    Affiliate = "affiliate"
    Regular = "regular"
