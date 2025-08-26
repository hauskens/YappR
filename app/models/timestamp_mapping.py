from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING, Dict, List, Any, Optional, Tuple
from .base import Base

if TYPE_CHECKING:
    from .video import Video


class TimestampMapping(Base):
    __tablename__ = "timestamp_mapping"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Source video (contains the "source of truth" transcriptions)
    source_video_id: Mapped[int] = mapped_column(
        ForeignKey("video.id"), index=True
    )
    source_video: Mapped["Video"] = relationship(
        foreign_keys=[source_video_id], 
        back_populates="source_mappings"
    )
    
    # Target video (available for playback)
    target_video_id: Mapped[int] = mapped_column(
        ForeignKey("video.id"), index=True
    )
    target_video: Mapped["Video"] = relationship(
        foreign_keys=[target_video_id],
        back_populates="target_mappings"
    )
    
    # Time ranges in seconds
    source_start_time: Mapped[float] = mapped_column(Float, default=0.0)
    source_end_time: Mapped[float] = mapped_column(Float)
    target_start_time: Mapped[float] = mapped_column(Float, default=0.0)
    target_end_time: Mapped[float] = mapped_column(Float)
    
    # Time offset (target video starts N seconds after source)
    time_offset: Mapped[float] = mapped_column(Float, default=0.0)
    
    # JSON data for cuts/edits - list of dicts with 'start' and 'duration' keys
    cuts_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Whether this mapping is active
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    def translate_source_to_target(self, source_timestamp: float) -> Optional[float]:
        """
        Translate a timestamp from source video to target video.
        
        Args:
            source_timestamp: Timestamp in seconds from source video
            
        Returns:
            Timestamp in target video, or None if not mappable
        """
        # Check if timestamp is within this mapping's source range
        if not (self.source_start_time <= source_timestamp <= self.source_end_time):
            return None
            
        # Calculate base target timestamp
        relative_time = source_timestamp - self.source_start_time
        target_timestamp = self.target_start_time + relative_time - self.time_offset
        
        # Apply cuts/edits if they exist
        if self.cuts_data and 'cuts' in self.cuts_data:
            cuts = self.cuts_data['cuts']
            total_cut_time = 0.0
            
            for cut in cuts:
                cut_start = cut.get('start', 0.0)
                cut_duration = cut.get('duration', 0.0)
                cut_end = cut_start + cut_duration
                
                # If the timestamp is after this cut, subtract the cut duration
                if source_timestamp > cut_end:
                    total_cut_time += cut_duration
                # If the timestamp is within the cut, it doesn't exist in target
                elif cut_start <= source_timestamp <= cut_end:
                    return None
                    
            target_timestamp -= total_cut_time
        
        # Ensure the result is within target range
        if target_timestamp < self.target_start_time or target_timestamp > self.target_end_time:
            return None
            
        return max(0.0, target_timestamp)
    
    def translate_target_to_source(self, target_timestamp: float) -> Optional[float]:
        """
        Translate a timestamp from target video to source video.
        
        Args:
            target_timestamp: Timestamp in seconds from target video
            
        Returns:
            Timestamp in source video, or None if not mappable
        """
        # Check if timestamp is within this mapping's target range
        if not (self.target_start_time <= target_timestamp <= self.target_end_time):
            return None
            
        # Start with relative timestamp in target
        relative_target_time = target_timestamp - self.target_start_time
        
        # Add back cuts to find original source time
        if self.cuts_data and 'cuts' in self.cuts_data:
            cuts = self.cuts_data['cuts']
            adjusted_time = relative_target_time
            
            # Sort cuts by start time
            sorted_cuts = sorted(cuts, key=lambda x: x.get('start', 0.0))
            
            for cut in sorted_cuts:
                cut_start = cut.get('start', 0.0) - self.source_start_time
                cut_duration = cut.get('duration', 0.0)
                
                # If we're past this cut point in the target video,
                # add back the cut duration to get source time
                if adjusted_time >= cut_start:
                    adjusted_time += cut_duration
            
            relative_target_time = adjusted_time
        
        # Calculate source timestamp
        source_timestamp = self.source_start_time + relative_target_time + self.time_offset
        
        # Ensure the result is within source range
        if source_timestamp < self.source_start_time or source_timestamp > self.source_end_time:
            return None
            
        return source_timestamp
    
    def adjust_time_offset(self, new_offset: float) -> None:
        """
        Manually adjust the time offset between source and target videos.
        
        Args:
            new_offset: New offset in seconds
        """
        self.time_offset = new_offset
    
    def add_cut(self, start_time: float, duration: float) -> None:
        """
        Add a cut/edit to the cuts_data.
        
        Args:
            start_time: Start time of cut in source video (seconds)
            duration: Duration of cut in seconds
        """
        if self.cuts_data is None:
            self.cuts_data = {'cuts': []}
        elif 'cuts' not in self.cuts_data:
            self.cuts_data['cuts'] = []
            
        self.cuts_data['cuts'].append({
            'start': start_time,
            'duration': duration
        })
        
        # Sort cuts by start time
        self.cuts_data['cuts'].sort(key=lambda x: x.get('start', 0.0))
    
    def remove_cut(self, start_time: float, duration: float, tolerance: float = 1.0) -> bool:
        """
        Remove a cut from cuts_data.
        
        Args:
            start_time: Start time of cut to remove
            duration: Duration of cut to remove
            tolerance: Tolerance for matching cut times
            
        Returns:
            True if cut was found and removed, False otherwise
        """
        if not self.cuts_data or 'cuts' not in self.cuts_data:
            return False
            
        cuts = self.cuts_data['cuts']
        for i, cut in enumerate(cuts):
            if (abs(cut.get('start', 0.0) - start_time) <= tolerance and
                abs(cut.get('duration', 0.0) - duration) <= tolerance):
                del cuts[i]
                return True
                
        return False
    
    def get_total_cut_duration(self) -> float:
        """
        Get the total duration of all cuts.
        
        Returns:
            Total cut duration in seconds
        """
        if not self.cuts_data or 'cuts' not in self.cuts_data:
            return 0.0
            
        return sum(cut.get('duration', 0.0) for cut in self.cuts_data['cuts'])
    
    def __repr__(self) -> str:
        return (f"<TimestampMapping(id={self.id}, "
                f"source={self.source_video_id}[{self.source_start_time}-{self.source_end_time}], "
                f"target={self.target_video_id}[{self.target_start_time}-{self.target_end_time}], "
                f"offset={self.time_offset})>")