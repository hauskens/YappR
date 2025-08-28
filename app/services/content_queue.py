from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select
from app.models import db
from app.models import ContentQueue, ContentQueueSubmission, Content, ContentQueueSubmissionSource, Video, ContentQueueSettings, WeightSettings, WeightSettingsBreakdown
from app.models.enums import VideoType
from app.services.video import VideoService
from app.logger import logger
from pydantic import ValidationError


class ContentQueueService:
    """Service class for content queue-related operations."""

    @staticmethod
    def get_all() -> Sequence[ContentQueue]:
        """Get all content queue entries."""
        return db.session.execute(
            select(ContentQueue).order_by(ContentQueue.id)
        ).scalars().all()

    @staticmethod
    def get_by_id(content_queue_id: int) -> ContentQueue:
        """Get content queue entry by ID."""
        return db.session.execute(
            select(ContentQueue).filter_by(id=content_queue_id)
        ).scalars().one()

    @staticmethod
    def get_by_broadcaster(broadcaster_id: int, watched: Optional[bool] = None,
                           skipped: Optional[bool] = None) -> Sequence[ContentQueue]:
        """Get content queue entries for a broadcaster with optional filters."""
        query = select(ContentQueue).filter_by(broadcaster_id=broadcaster_id)

        if watched is not None:
            query = query.filter_by(watched=watched)
        if skipped is not None:
            query = query.filter_by(skipped=skipped)

        return db.session.execute(
            query.order_by(ContentQueue.score.desc(), ContentQueue.id)
        ).scalars().all()

    @staticmethod
    def get_unwatched_by_broadcaster(broadcaster_id: int) -> Sequence[ContentQueue]:
        """Get unwatched content queue entries for a broadcaster."""
        return ContentQueueService.get_by_broadcaster(
            broadcaster_id, watched=False, skipped=False
        )

    @staticmethod
    def create(broadcaster_id: int, content_id: int, content_timestamp: Optional[int] = None,
               score: float = 0.0) -> ContentQueue:
        """Create a new content queue entry."""
        content_queue = ContentQueue(
            broadcaster_id=broadcaster_id,
            content_id=content_id,
            content_timestamp=content_timestamp,
            watched=False,
            skipped=False,
            score=score
        )
        db.session.add(content_queue)
        db.session.commit()
        logger.info(
            f"Created content queue entry {content_queue.id} for broadcaster {broadcaster_id}")
        return content_queue

    @staticmethod
    def mark_watched(content_queue_id: int, watched_at: Optional[datetime] = None) -> ContentQueue:
        """Mark a content queue entry as watched."""
        content_queue = ContentQueueService.get_by_id(content_queue_id)
        content_queue.watched = True
        content_queue.watched_at = watched_at or datetime.utcnow()
        content_queue.skipped = False
        db.session.commit()
        logger.info(
            f"Marked content queue entry {content_queue_id} as watched")
        return content_queue

    @staticmethod
    def mark_skipped(content_queue_id: int) -> ContentQueue:
        """Mark a content queue entry as skipped."""
        content_queue = ContentQueueService.get_by_id(content_queue_id)
        content_queue.skipped = True
        content_queue.watched = False
        content_queue.watched_at = None
        db.session.commit()
        logger.info(
            f"Marked content queue entry {content_queue_id} as skipped")
        return content_queue

    @staticmethod
    def update_score(content_queue_id: int, score: float) -> ContentQueue:
        """Update the score of a content queue entry."""
        content_queue = ContentQueueService.get_by_id(content_queue_id)
        content_queue.score = score
        db.session.commit()
        logger.info(
            f"Updated score for content queue entry {content_queue_id} to {score}")
        return content_queue

    @staticmethod
    def delete(content_queue_id: int) -> None:
        """Delete a content queue entry."""
        content_queue = ContentQueueService.get_by_id(content_queue_id)
        db.session.delete(content_queue)
        db.session.commit()
        logger.info(f"Deleted content queue entry {content_queue_id}")

    @staticmethod
    def get_top_scored(broadcaster_id: int, limit: int = 10) -> Sequence[ContentQueue]:
        """Get top scored unwatched content queue entries for a broadcaster."""
        return db.session.execute(
            select(ContentQueue)
            .filter_by(broadcaster_id=broadcaster_id, watched=False, skipped=False)
            .order_by(ContentQueue.score.desc())
            .limit(limit)
        ).scalars().all()

    @staticmethod
    def get_vod_timestamp_url(content_queue_id: int, time_shift: float = 60) -> Optional[str]:
        """Find the broadcaster's video that was live when this clip was marked as watched
        and return a URL with the timestamp.

        The function finds the closest previous watched item with the same broadcaster_id
        and uses that time for the timestamp URL. If the time difference between this item
        and the previous one is longer than 90 seconds + video duration, it uses that instead.

        Args:
            content_queue_id: ID of the content queue entry
            time_shift: Default time shift in seconds (used as fallback if no previous item found)

        Returns:
            URL string with timestamp or None if no matching video found
        """
        content_queue = ContentQueueService.get_by_id(content_queue_id)

        if not content_queue.watched or not content_queue.watched_at:
            return None

        # Find the closest previous watched item with the same broadcaster_id
        previous_item = db.session.execute(
            select(ContentQueue).filter(
                ContentQueue.broadcaster_id == content_queue.broadcaster_id,
                ContentQueue.watched == True,
                ContentQueue.watched_at < content_queue.watched_at
            ).order_by(ContentQueue.watched_at.desc())
        ).scalars().first()

        # Calculate the time difference to use for the offset
        if previous_item and previous_item.watched_at:
            # Calculate time difference in seconds between current and previous item
            content_duration = content_queue.content.duration or 0

            # Ensure both timestamps are timezone-aware for comparison
            current_watched_at = content_queue.watched_at
            previous_watched_at = previous_item.watched_at
            
            # If either timestamp is naive, make them both timezone-naive for comparison
            if current_watched_at.tzinfo is None or previous_watched_at.tzinfo is None:
                if current_watched_at.tzinfo is not None:
                    current_watched_at = current_watched_at.replace(tzinfo=None)
                if previous_watched_at.tzinfo is not None:
                    previous_watched_at = previous_watched_at.replace(tzinfo=None)

            # Subtract content duration from the time difference
            time_diff = (current_watched_at - previous_watched_at).total_seconds()

            # Ensure time_diff is at least 0
            time_diff = max(0, time_diff)

            # Use the minimum of the actual time difference and 90 seconds
            time_shift = min(time_diff, 90 + content_duration)

        # Find videos from this broadcaster's channels that were live when the clip was watched
        for channel in content_queue.broadcaster.channels:
            # Look for videos that might include this timestamp
            # We need to find videos that were live when the clip was watched
            candidate_videos = db.session.execute(
                select(Video).filter(
                    Video.channel_id == channel.id,
                    Video.video_type == VideoType.VOD  # Ensure it's a VOD
                )
            ).scalars().all()

            for video in candidate_videos:
                # Check if video was live when clip was watched
                video_end_time = video.uploaded + \
                    timedelta(seconds=video.duration)
                
                # Ensure timezone consistency for video timestamp comparison
                watched_at_for_comparison = content_queue.watched_at
                video_uploaded_for_comparison = video.uploaded
                
                # Make both timezone-naive if either is naive
                if watched_at_for_comparison.tzinfo is None or video_uploaded_for_comparison.tzinfo is None:
                    if watched_at_for_comparison.tzinfo is not None:
                        watched_at_for_comparison = watched_at_for_comparison.replace(tzinfo=None)
                    if video_uploaded_for_comparison.tzinfo is not None:
                        video_uploaded_for_comparison = video_uploaded_for_comparison.replace(tzinfo=None)
                        video_end_time = video_uploaded_for_comparison + timedelta(seconds=video.duration)
                
                if video_uploaded_for_comparison <= watched_at_for_comparison <= video_end_time:
                    # Calculate seconds from start of video to when clip was watched
                    seconds_offset = (
                        watched_at_for_comparison - video_uploaded_for_comparison -
                        timedelta(seconds=time_shift)
                    ).total_seconds()

                    # Generate URL with timestamp
                    return VideoService.get_url_with_timestamp(video, seconds_offset)

        return None


class ContentService:
    """Service class for content-related operations."""

    @staticmethod
    def get_all() -> Sequence[Content]:
        """Get all content entries."""
        return db.session.execute(
            select(Content).order_by(Content.id)
        ).scalars().all()

    @staticmethod
    def get_by_id(content_id: int) -> Content:
        """Get content by ID."""
        return db.session.execute(
            select(Content).filter_by(id=content_id)
        ).scalars().one()

    @staticmethod
    def get_by_url(url: str) -> Optional[Content]:
        """Get content by URL."""
        return db.session.execute(
            select(Content).filter_by(url=url)
        ).scalars().one_or_none()

    @staticmethod
    def get_by_stripped_url(stripped_url: str) -> Optional[Content]:
        """Get content by stripped URL."""
        return db.session.execute(
            select(Content).filter_by(stripped_url=stripped_url)
        ).scalars().one_or_none()

    @staticmethod
    def create(url: str, stripped_url: str, title: str, channel_name: str,
               duration: Optional[int] = None, thumbnail_url: Optional[str] = None,
               author: Optional[str] = None, created_at: Optional[datetime] = None) -> Content:
        """Create a new content entry."""
        content = Content(
            url=url,
            stripped_url=stripped_url,
            title=title,
            channel_name=channel_name,
            duration=duration,
            thumbnail_url=thumbnail_url,
            author=author,
            created_at=created_at
        )
        db.session.add(content)
        db.session.commit()
        logger.info(f"Created content entry {content.id} for URL {url}")
        return content

    @staticmethod
    def update(content_id: int, **kwargs) -> Content:
        """Update content entry fields."""
        content = ContentService.get_by_id(content_id)

        for key, value in kwargs.items():
            if hasattr(content, key):
                setattr(content, key, value)

        db.session.commit()
        logger.info(f"Updated content entry {content_id}")
        return content

    @staticmethod
    def delete(content_id: int) -> None:
        """Delete a content entry."""
        content = ContentService.get_by_id(content_id)
        db.session.delete(content)
        db.session.commit()
        logger.info(f"Deleted content entry {content_id}")

    @staticmethod
    def search_by_title(query: str, limit: int = 20) -> Sequence[Content]:
        """Search content by title."""
        return db.session.execute(
            select(Content)
            .filter(Content.title.ilike(f'%{query}%'))
            .order_by(Content.created_at.desc())
            .limit(limit)
        ).scalars().all()

    @staticmethod
    def search_by_channel(channel_name: str, limit: int = 20) -> Sequence[Content]:
        """Search content by channel name."""
        return db.session.execute(
            select(Content)
            .filter(Content.channel_name.ilike(f'%{channel_name}%'))
            .order_by(Content.created_at.desc())
            .limit(limit)
        ).scalars().all()


class WeightSettingsService:
    """Service class for weight settings-related operations."""

    @staticmethod
    def get_by_broadcaster(broadcaster_id: int) -> WeightSettings:
        """Get weight settings by broadcaster ID."""
        content_queue_settings = db.session.execute(
            select(ContentQueueSettings).filter_by(broadcaster_id=broadcaster_id)
        ).scalars().one_or_none()

        if not content_queue_settings:
            content_queue_settings = ContentQueueSettings(broadcaster_id=broadcaster_id)
            db.session.add(content_queue_settings)
            db.session.commit()

        try:
            weight_settings = WeightSettings.model_validate(content_queue_settings.weight_settings)
        except ValidationError as e:
            logger.warning(f"Failed to validate weight settings for broadcaster {broadcaster_id}, using default settings: {e}")
            weight_settings = WeightSettings()
        return weight_settings

    @staticmethod
    def update_weight_settings(broadcaster_id: int, weight_settings: WeightSettings) -> None:
        """Update weight settings for a broadcaster."""
        content_queue_settings = db.session.execute(
            select(ContentQueueSettings).filter_by(broadcaster_id=broadcaster_id)
        ).scalars().one()
        content_queue_settings.weight_settings = weight_settings.model_dump()
        db.session.commit()

    @staticmethod
    def get_default_weight_settings() -> WeightSettings:
        """Get default weight settings."""
        return WeightSettings()

    @staticmethod
    def reset_weight_settings(broadcaster_id: int) -> None:
        """Reset weight settings for a broadcaster."""
        content_queue_settings = db.session.execute(
            select(ContentQueueSettings).filter_by(broadcaster_id=broadcaster_id)
        ).scalars().one()
        content_queue_settings.weight_settings = WeightSettings().model_dump()
        db.session.commit()

    @staticmethod
    def calculate_score(weight_settings: WeightSettings, base_popularity: float, age_minutes: int, 
                       duration_seconds: int = 0, is_trusted: bool = False) -> tuple[float, WeightSettingsBreakdown]:
        """
        Calculate the final score for a content item with detailed breakdown.
        
        Args:
            weight_settings: WeightSettings instance with preferences
            base_popularity: Base popularity score (usually from submission count/weights)
            age_minutes: Age of content in minutes
            duration_seconds: Duration of content in seconds
            is_trusted: Whether submitter is trusted (VIP/MOD)
            
        Returns:
            tuple: (final_score, breakdown_dict)
        """
        breakdown: WeightSettingsBreakdown = WeightSettingsBreakdown(
            base_popularity=base_popularity,
            age_minutes=age_minutes,
            components=[],
            multipliers={},
            duration_seconds=duration_seconds
        )
        
        # Start with base popularity
        score = base_popularity
        breakdown.components.append(f"Base popularity: {base_popularity:.0f}")
        
        # Apply popularity adjustment
        popularity_multiplier = weight_settings.get_popularity_multiplier(base_popularity)
        if popularity_multiplier != base_popularity:
            score = popularity_multiplier
            breakdown.multipliers['popularity'] = popularity_multiplier / base_popularity if base_popularity > 0 else 1.0
            breakdown.components.append(f"Popularity adjustment: ×{breakdown.multipliers['popularity']:.1f} = {score:.1f}")
        
        # Apply freshness boost
        freshness_multiplier = weight_settings.get_freshness_multiplier(age_minutes)
        if freshness_multiplier != 1.0:
            score *= freshness_multiplier
            breakdown.multipliers['freshness'] = freshness_multiplier
            breakdown.components.append(f"Freshness boost: ×{freshness_multiplier:.1f} = {score:.1f}")
        
        # Apply duration preference
        if duration_seconds:
            duration_multiplier = weight_settings.get_short_duration_multiplier() if duration_seconds <= weight_settings.short_clip_threshold_seconds else 1.0
        else:
            duration_multiplier = 1.0
            
        if duration_multiplier != 1.0:
            score *= duration_multiplier
            breakdown.multipliers['duration'] = duration_multiplier
            breakdown.components.append(f"Short duration boost: ×{duration_multiplier:.1f} = {score:.1f}")
        
        # Apply viewer priority boost
        viewer_multiplier = weight_settings.get_viewer_priority_multiplier(is_trusted)
        if viewer_multiplier != 1.0:
            score *= viewer_multiplier
            breakdown.multipliers['viewer_priority'] = viewer_multiplier
            breakdown.components.append(f"Trusted viewer boost: ×{viewer_multiplier:.1f} = {score:.1f}")
        
        breakdown.final_score = score
        return score, breakdown

    @staticmethod
    def get_score_breakdown(content_queue_item: ContentQueue, broadcaster_id: int) -> WeightSettingsBreakdown:
        """Get detailed breakdown of how a content queue item's score is calculated using WeightSettings."""
        weight_settings = WeightSettingsService.get_by_broadcaster(broadcaster_id)
        
        # Calculate age in minutes
        if content_queue_item.submissions:
            earliest_submission = min(content_queue_item.submissions, key=lambda s: s.submitted_at)
            age_minutes = int((datetime.now(timezone.utc) - earliest_submission.submitted_at).total_seconds() / 60)
        else:
            age_minutes = 0
        
        # Get base popularity (total weight from submissions)
        base_popularity = content_queue_item.total_weight if hasattr(content_queue_item, 'total_weight') else len(content_queue_item.submissions)
        
        # Check if user is trusted (VIP/MOD) - simplified for now
        # TODO: Implement trusted user logic by looking at external user roles
        is_trusted = False
        
        # Get duration in seconds
        duration_seconds = content_queue_item.content.duration if content_queue_item.content.duration is not None else 0
        
        # Calculate score and get breakdown
        final_score, breakdown = WeightSettingsService.calculate_score(
            weight_settings=weight_settings,
            base_popularity=base_popularity,
            age_minutes=age_minutes,
            duration_seconds=duration_seconds,
            is_trusted=is_trusted,
        )
        
        
        
        return breakdown


class ContentQueueSubmissionService:
    """Service class for content queue submission-related operations."""

    @staticmethod
    def get_all() -> Sequence[ContentQueueSubmission]:
        """Get all content queue submissions."""
        return db.session.execute(
            select(ContentQueueSubmission).order_by(
                ContentQueueSubmission.submitted_at.desc())
        ).scalars().all()

    @staticmethod
    def get_by_id(submission_id: int) -> ContentQueueSubmission:
        """Get content queue submission by ID."""
        return db.session.execute(
            select(ContentQueueSubmission).filter_by(id=submission_id)
        ).scalars().one()

    @staticmethod
    def get_by_content_queue(content_queue_id: int) -> Sequence[ContentQueueSubmission]:
        """Get all submissions for a content queue entry."""
        return db.session.execute(
            select(ContentQueueSubmission)
            .filter_by(content_queue_id=content_queue_id)
            .order_by(ContentQueueSubmission.submitted_at.desc())
        ).scalars().all()

    @staticmethod
    def get_by_user(user_id: int) -> Sequence[ContentQueueSubmission]:
        """Get all submissions by a user."""
        return db.session.execute(
            select(ContentQueueSubmission)
            .filter_by(user_id=user_id)
            .order_by(ContentQueueSubmission.submitted_at.desc())
        ).scalars().all()

    @staticmethod
    def create(content_queue_id: int, content_id: int, user_id: int,
               submission_source_type: ContentQueueSubmissionSource, submission_source_id: int,
               weight: float, user_comment: Optional[str] = None,
               submitted_at: Optional[datetime] = None) -> ContentQueueSubmission:
        """Create a new content queue submission."""
        submission = ContentQueueSubmission(
            content_queue_id=content_queue_id,
            content_id=content_id,
            user_id=user_id,
            submission_source_type=submission_source_type,
            submission_source_id=submission_source_id,
            weight=weight,
            user_comment=user_comment,
            submitted_at=submitted_at or datetime.utcnow()
        )
        db.session.add(submission)
        db.session.commit()
        logger.info(f"Created content queue submission {submission.id}")
        return submission

    @staticmethod
    def update_weight(submission_id: int, weight: float) -> ContentQueueSubmission:
        """Update the weight of a submission."""
        submission = ContentQueueSubmissionService.get_by_id(submission_id)
        submission.weight = weight
        db.session.commit()
        logger.info(
            f"Updated weight for submission {submission_id} to {weight}")
        return submission

    @staticmethod
    def update_comment(submission_id: int, user_comment: Optional[str]) -> ContentQueueSubmission:
        """Update the user comment of a submission."""
        submission = ContentQueueSubmissionService.get_by_id(submission_id)
        submission.user_comment = user_comment
        db.session.commit()
        logger.info(f"Updated comment for submission {submission_id}")
        return submission

    @staticmethod
    def delete(submission_id: int) -> None:
        """Delete a content queue submission."""
        submission = ContentQueueSubmissionService.get_by_id(submission_id)
        db.session.delete(submission)
        db.session.commit()
        logger.info(f"Deleted content queue submission {submission_id}")
