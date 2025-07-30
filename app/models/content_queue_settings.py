from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Boolean, Integer, Text
from .base import Base
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .broadcaster import Broadcaster


class WeightSettings(BaseModel):
    """
    Pydantic model for queue sorting preferences.

    This model defines how the clip queue should be prioritized and sorted.
    All intensity values are normalized to 0.0-1.0 range for consistency.
    """

    # Boolean preferences - enable/disable features
    prefer_shorter: bool = Field(
        default=False,
        description="Boost clips under X seconds in duration",

    )

    keep_fresh: bool = Field(
        default=True,
        description="Prioritize recently submitted content"
    )

    ignore_popularity: bool = Field(
        default=False,
        description="Multiple people submitting same clip will not increase its priority"
    )

    viewer_priority: bool = Field(
        default=False,
        description="Give higher priority to VIP/MOD submissions"
    )

    # Intensity settings - all normalized to 0.0-1.0 range
    prefer_shorter_intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Intensity of short content preference (0.0=none, 1.0=shorter clips get more priority)"
    )

    keep_fresh_intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Intensity of freshness boost (0.0=none, 1.0=newer clips get more priority)"
    )

    ignore_popularity_intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How much to reduce popularity impact (0.0=no reduction, 1.0=maximum reduction)"
    )

    viewer_priority_intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Intensity of viewer priority (0.0=none, 1.0=VIP/MOD submissions get more priority)"
    )

    # Advanced settings
    short_clip_threshold_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Duration threshold for considering a clip 'short' (seconds)"
    )

    freshness_window_minutes: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Time window for considering content 'fresh' (minutes)"
    )

    def get_short_duration_multiplier(self) -> float:
        """
        Calculate the multiplier for short content based on intensity.

        Returns:
            float: Multiplier between 1.0 (no boost) and 1.5 (max boost)
        """
        if not self.prefer_shorter:
            return 1.0
        return 1.0 + (self.prefer_shorter_intensity * 0.5)

    def get_freshness_multiplier(self, age_minutes: int) -> float:
        """
        Calculate freshness boost based on content age and intensity.

        Args:
            age_minutes: Age of content in minutes

        Returns:
            float: Multiplier between 1.0 (no boost) and 2.0 (max boost)
        """
        if not self.keep_fresh or age_minutes > self.freshness_window_minutes:
            return 1.0
        freshness_ratio = 1.0 - (age_minutes / self.freshness_window_minutes)
        return 1.0 + (self.keep_fresh_intensity * freshness_ratio)

    def get_popularity_multiplier(self, base_popularity: float) -> float:
        """
        Calculate adjusted popularity based on ignore_popularity setting.

        Args:
            base_popularity: Original popularity score

        Returns:
            float: Adjusted popularity score
        """
        if not self.ignore_popularity:
            return base_popularity
        return 1.0 + (base_popularity - 1.0) * (1.0 - self.ignore_popularity_intensity)


    def get_viewer_priority_multiplier(self, is_trusted: bool) -> float:
        """
        Calculate boost for trusted viewers.

        Args:
            is_trusted: Whether the submitter is trusted

        Returns:
            float: Multiplier between 1.0 (no boost) and 1.5 (max boost)
        """
        if not self.viewer_priority or not is_trusted:
            return 1.0
        return 1.0 + (self.viewer_priority_intensity * 0.5)

    def get_active_preferences(self) -> dict[str, float]:
        """
        Get only the preferences that are currently enabled.

        Returns:
            Dictionary of active preference names and their intensities
        """
        active = {}

        if self.prefer_shorter:
            active['prefer_shorter'] = self.prefer_shorter_intensity
        if self.keep_fresh:
            active['keep_fresh'] = self.keep_fresh_intensity
        if self.ignore_popularity:
            active['ignore_popularity'] = self.ignore_popularity_intensity
        if self.viewer_priority:
            active['viewer_priority'] = self.viewer_priority_intensity
        return active

    def to_json(self) -> dict[str, Any]:
        return self.model_dump()

class WeightSettingsBreakdown(BaseModel):
    base_popularity: float
    age_minutes: int
    components: list[str]
    multipliers: dict[str, float] 
    final_score: float | None = None
    duration_seconds: int = 0


    def get_age_formatted(self) -> str:
        if self.age_minutes < 60:
            age_formatted = f"{self.age_minutes:.1f} minutes"
        elif self.age_minutes < 1440:  # 24 hours
            age_formatted = f"{self.age_minutes/60:.1f} hours"
        else:
            age_formatted = f"{self.age_minutes/1440:.1f} days"
        return age_formatted

    def get_duration_formatted(self) -> str:
        return f"{self.duration_seconds//60}:{self.duration_seconds%60:02d}" if self.duration_seconds else "N/A"

class ContentQueueSettings(Base):
    __tablename__ = "content_queue_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcaster_id: Mapped[int] = mapped_column(ForeignKey("broadcaster.id"))
    broadcaster: Mapped["Broadcaster"] = relationship()
    prefer_shorter_content: Mapped[bool] = mapped_column(
        Boolean, default=False)
    view_count_min: Mapped[int] = mapped_column(Integer, default=0)
    allowed_platforms: Mapped[str] = mapped_column(Text, default="")
    weight_settings: Mapped[dict[str, Any]|None] = mapped_column(JSONB, nullable=True)

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
