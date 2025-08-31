from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from sqlalchemy import and_
from app.models import db
from app.models.video import Video
from app.models.channel import ChannelEvent
from app.models.enums import ChannelEventType
from app.utils import extract_date_from_video_title
from app.logger import logger


class VideoDateEstimationService:
    """Service for estimating video upload times using title dates and live events."""
    
    @staticmethod
    def estimate_upload_times_for_channel(channel_id: int, date_margin_hours: int = 48, duration_margin_seconds: int = 20) -> Dict[str, int]:
        """
        Estimate upload times for all videos in a channel by matching title dates with live events.
        
        Args:
            channel_id: Channel ID to process
            date_margin_hours: Maximum hours between title date and live event
            duration_margin_seconds: Maximum seconds difference between video and stream duration
            
        Returns:
            Dictionary with 'updated_count' and 'total_processed'
        """
        logger.info(f"Starting bulk date estimation for channel {channel_id}")
        
        # Get channel info to check for source channel
        from app.models.channel import Channels
        channel = db.session.query(Channels).filter_by(id=channel_id).first()
        if not channel:
            logger.error(f"Channel {channel_id} not found")
            return {"updated_count": 0, "total_processed": 0}
        
        # Determine which channel to use for event lookup
        event_channel_id = channel.source_channel_id if channel.source_channel_id else channel_id
        event_channel_name = channel.source_channel.name if channel.source_channel else channel.name
        
        logger.info(f"Using channel {event_channel_id} ({event_channel_name}) for live event lookup")
        
        # Get all videos for the channel that don't have estimated_upload_time set
        videos = db.session.query(Video).filter(
            and_(
                Video.channel_id == channel_id,
                Video.estimated_upload_time.is_(None)
            )
        ).all()
        
        if not videos:
            logger.info(f"No videos without estimated upload time found for channel {channel_id}")
            return {"updated_count": 0, "total_processed": 0}
        
        logger.info(f"Processing {len(videos)} videos for date estimation")
        
        # Get all live and offline events for the event channel (could be source channel)
        events = db.session.query(ChannelEvent).filter(
            and_(
                ChannelEvent.channel_id == event_channel_id,
                ChannelEvent.event_type.in_([ChannelEventType.Live, ChannelEventType.Offline])
            )
        ).order_by(ChannelEvent.timestamp).all()
        
        if not events:
            logger.info(f"No live/offline events found for event channel {event_channel_id} ({event_channel_name})")
            return {"updated_count": 0, "total_processed": len(videos)}
        
        # Parse events into live/offline pairs
        stream_sessions = VideoDateEstimationService._parse_stream_sessions(events)
        logger.info(f"Found {len(stream_sessions)} stream sessions to match against")
        
        updated_count = 0
        
        for video in videos:
            try:
                # Extract date from video title
                title_date = extract_date_from_video_title(video.title)
                
                if not title_date:
                    logger.debug(f"No date found in title: {video.title[:50]}...")
                    continue
                
                # Find matching stream session within the margin
                matching_session = VideoDateEstimationService._find_matching_stream_session(
                    title_date, video.duration, stream_sessions, date_margin_hours, duration_margin_seconds
                )
                
                if matching_session:
                    live_event, offline_event, stream_duration = matching_session
                    # Update the video's estimated_upload_time
                    video.estimated_upload_time = live_event.timestamp
                    db.session.add(video)
                    updated_count += 1
                    
                    duration_diff = abs(video.duration - stream_duration.total_seconds()) if stream_duration else float('inf')
                    
                    logger.info(
                        f"Updated video '{video.title[:50]}...' with estimated upload time {live_event.timestamp}",
                        extra={
                            "video_id": video.id,
                            "video_duration": video.duration,
                            "stream_duration": stream_duration.total_seconds() if stream_duration else None,
                            "duration_difference": duration_diff,
                            "title_date": title_date.isoformat(),
                            "live_event_time": live_event.timestamp.isoformat(),
                            "offline_event_time": offline_event.timestamp.isoformat() if offline_event else None
                        }
                    )
                else:
                    logger.debug(
                        f"No matching stream session found within {date_margin_hours}h of title date {title_date} for video: {video.title[:50]}..."
                    )
                    
            except Exception as e:
                logger.error(
                    f"Error processing video {video.id}: {e}",
                    extra={"video_id": video.id, "title": video.title[:100]}
                )
                continue
        
        # Commit all changes
        try:
            db.session.commit()
            logger.info(f"Successfully updated {updated_count} out of {len(videos)} videos")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to commit video updates: {e}")
            raise
        
        return {"updated_count": updated_count, "total_processed": len(videos)}
    
    @staticmethod
    def _parse_stream_sessions(events: list[ChannelEvent]) -> list[Tuple[ChannelEvent, ChannelEvent, timedelta]]:
        """
        Parse events into stream sessions (live -> offline pairs).
        
        Returns:
            List of tuples: (live_event, offline_event, duration)
        """
        sessions = []
        current_live = None
        
        for event in events:
            if event.event_type == ChannelEventType.Live:
                # If we already have a live event without an offline, save it
                current_live = event
            elif event.event_type == ChannelEventType.Offline and current_live:
                # Found offline event for current live session
                duration = event.timestamp - current_live.timestamp
                sessions.append((current_live, event, duration))
                current_live = None
        
        return sessions
    
    @staticmethod
    def _find_matching_stream_session(
        target_date: datetime,
        video_duration: float,
        stream_sessions: List[Tuple[ChannelEvent, ChannelEvent, timedelta]],
        date_margin_hours: int,
        duration_margin_seconds: int = 20
    ) -> Tuple[ChannelEvent, ChannelEvent, timedelta] | None:
        """
        Find a stream session that matches the video by date and duration.
        
        Args:
            target_date: Date extracted from video title (usually at 00:00:00)
            video_duration: Duration of the video in seconds
            stream_sessions: List of (live_event, offline_event, duration) tuples
            date_margin_hours: Maximum time difference between title date and stream start
            duration_margin_seconds: Maximum duration difference in seconds (default 20)
            
        Returns:
            Matching session tuple or None
        """
        best_match = None
        best_score = float('inf')  # Lower is better
        
        for live_event, offline_event, stream_duration in stream_sessions:
            # Check date proximity - prioritize same day
            time_diff = abs(target_date - live_event.timestamp)
            
            # Skip if outside date margin
            if time_diff > timedelta(hours=date_margin_hours):
                continue
            
            # Calculate date score (same day = 0, otherwise hours difference)
            if live_event.timestamp.date() == target_date.date():
                date_score = 0.0  # Perfect date match
            else:
                date_score = time_diff.total_seconds() / float(3600)  # Hours difference
            
            # Calculate duration score if we have both live and offline events
            duration_score = float('inf')  # Default to high score if no duration available
            if stream_duration is not None:
                duration_diff = abs(video_duration - stream_duration.total_seconds())
                if duration_diff <= duration_margin_seconds:
                    duration_score = duration_diff  # Exact duration difference in seconds
                else:
                    # Duration too different, but still consider for date-only matching
                    duration_score = 1000 + duration_diff  # Penalize but don't exclude
            
            # Combined score: prioritize date match, then duration match
            combined_score = date_score * 100 + duration_score
            
            if combined_score < best_score:
                best_match = (live_event, offline_event, stream_duration)
                best_score = combined_score
                
                logger.debug(
                    f"Better match found: date_score={date_score:.1f}h, duration_score={duration_score:.1f}s, combined={combined_score:.1f}",
                    extra={
                        "live_timestamp": live_event.timestamp.isoformat(),
                        "video_duration": video_duration,
                        "stream_duration": stream_duration.total_seconds() if stream_duration else None
                    }
                )
        
        return best_match
    
    @staticmethod
    def _find_closest_live_event(
        target_date: datetime, 
        live_events: List[ChannelEvent], 
        margin_hours: int
    ) -> Optional[ChannelEvent]:
        """
        Find the closest live event to a target date within the specified margin.
        
        Args:
            target_date: Date extracted from video title
            live_events: List of live events sorted by timestamp
            margin_hours: Maximum allowed time difference in hours
            
        Returns:
            Closest ChannelEvent or None if no event found within margin
        """
        closest_event = None
        min_time_diff = timedelta(hours=margin_hours + 1)  # Start with impossible value
        
        for event in live_events:
            time_diff = abs(target_date - event.timestamp)
            
            # Check if this event is within margin and closer than previous best
            if time_diff <= timedelta(hours=margin_hours) and time_diff < min_time_diff:
                closest_event = event
                min_time_diff = time_diff
        
        return closest_event