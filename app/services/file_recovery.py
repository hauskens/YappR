"""
File recovery service for restoring metadata and audio files.
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy_file import File

from app.models import db, Video
from app.models.config import config
from app.logger import logger


class FileRecoveryService:
    """Service for recovering files from restore directory."""
    
    @staticmethod
    def recover_files() -> Dict[str, any]:
        """
        Recover files from the restore directory.
        
        Looks for *.metadata.json files in the restore folder, extracts video IDs
        from filenames, matches them with existing videos, and attaches audio files.
        
        Returns:
            Dict with recovery statistics and results
        """
        restore_path = Path(config.storage_location) / "restore"
        
        if not restore_path.exists():
            logger.warning(f"Restore directory does not exist: {restore_path}")
            return {
                "success": False,
                "error": f"Restore directory not found: {restore_path}",
                "processed": 0,
                "matched": 0,
                "attached": 0
            }
        
        results = {
            "success": True,
            "processed": 0,
            "matched": 0,
            "attached": 0,
            "errors": [],
            "details": []
        }
        
        # Find all metadata files
        metadata_files = list(restore_path.glob("*.metadata.json"))
        logger.info(f"Found {len(metadata_files)} metadata files in {restore_path}")
        
        for metadata_file in metadata_files:
            try:
                result = FileRecoveryService._process_metadata_file(metadata_file)
                results["processed"] += 1
                results["details"].append(result)
                
                if result["matched"]:
                    results["matched"] += 1
                if result["attached"]:
                    results["attached"] += 1
                    
            except Exception as e:
                error_msg = f"Error processing {metadata_file.name}: {str(e)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
        
        logger.info(f"Recovery complete: {results['matched']}/{results['processed']} files matched, {results['attached']} audio files attached")
        return results
    
    @staticmethod
    def _process_metadata_file(metadata_file: Path) -> Dict[str, any]:
        """
        Process a single metadata file.
        
        Args:
            metadata_file: Path to the metadata.json file
            
        Returns:
            Dict with processing results for this file
        """
        result = {
            "metadata_file": metadata_file.name,
            "video_id": None,
            "matched": False,
            "attached": False,
            "error": None
        }
        
        try:
            # Read metadata
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            filename = metadata.get("filename", "")
            content_type = metadata.get("content_type", "")
            
            # Extract video ID from filename
            video_id = FileRecoveryService._extract_video_id(filename)
            result["video_id"] = video_id
            
            if not video_id:
                result["error"] = f"Could not extract video ID from filename: {filename}"
                return result
            
            # Find matching video in database
            video = db.session.execute(
                select(Video).filter_by(platform_ref=video_id)
            ).scalars().one_or_none()
            
            if not video:
                result["error"] = f"No video found with platform_ref: {video_id}"
                return result
                
            result["matched"] = True
            logger.info(f"Found matching video: {video.title} (ID: {video.id}) for {video_id}")
            
            # Check if it's an audio file and attach it
            if FileRecoveryService._is_audio_file(content_type, filename):
                success = FileRecoveryService._attach_audio_file(video, metadata_file, filename)
                if success:
                    result["attached"] = True
                    logger.info(f"Attached audio file to video {video.id}: {filename}")
                else:
                    result["error"] = f"Failed to attach audio file: {filename}"
            else:
                result["error"] = f"File is not an audio file: {filename} ({content_type})"
                
        except json.JSONDecodeError as e:
            result["error"] = f"Invalid JSON in metadata file: {str(e)}"
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            
        return result
    
    @staticmethod
    def _extract_video_id(filename: str) -> Optional[str]:
        """
        Extract video ID from filename.
        
        Looks for YouTube video IDs (11 characters) in the filename.
        Examples:
        - "cacheY5kyCQTJH24.vtt" -> "Y5kyCQTJH24"  
        - "S4xZ-bkBliQ.webm" -> "S4xZ-bkBliQ"
        
        Args:
            filename: The original filename from metadata
            
        Returns:
            Video ID string or None if not found
        """
        # YouTube video IDs are 11 characters long, alphanumeric + hyphens + underscores
        # Pattern matches 11 character strings that could be YouTube video IDs
        youtube_id_pattern = r'([a-zA-Z0-9_-]{11})'
        
        matches = re.findall(youtube_id_pattern, filename)
        
        # Return the first match that looks like a YouTube video ID
        for match in matches:
            # Additional validation: YouTube IDs typically don't start with cache
            if not match.startswith('cache'):
                return match
        
        # If no good match found, try the first match anyway
        if matches:
            return matches[0]
            
        return None
    
    @staticmethod  
    def _is_audio_file(content_type: str, filename: str) -> bool:
        """
        Check if the file is an audio file based on content type and extension.
        
        Args:
            content_type: MIME type from metadata
            filename: Original filename
            
        Returns:
            True if file appears to be audio
        """
        # Check content type
        if content_type.startswith('audio/'):
            return True
            
        # Check for video files that contain audio (common for downloads)
        video_with_audio_types = [
            'video/webm',
            'video/mp4', 
            'video/mkv',
            'application/octet-stream'  # Sometimes used for media files
        ]
        
        if content_type in video_with_audio_types:
            return True
            
        # Check file extension as fallback
        audio_extensions = ['.webm', '.mp4', '.mkv', '.m4a', '.wav', '.mp3', '.ogg', '.aac']
        file_ext = Path(filename).suffix.lower()
        
        return file_ext in audio_extensions
    
    @staticmethod
    def _attach_audio_file(video: Video, metadata_file: Path, filename: str) -> bool:
        """
        Attach an audio file to a video.
        
        Args:
            video: Video object to attach audio to
            metadata_file: Path to metadata file (used to find actual file)
            filename: Original filename
            
        Returns:
            True if successfully attached
        """
        try:
            # The actual file should be in the same directory with the same name as metadata file
            # but without the .metadata.json extension
            file_uuid = metadata_file.stem.replace('.metadata', '')
            actual_file_path = metadata_file.parent / file_uuid
            
            if not actual_file_path.exists():
                logger.error(f"Audio file not found: {actual_file_path}")
                return False
            
            # Check if video already has audio
            if video.audio is not None:
                logger.warning(f"Video {video.id} already has audio file, skipping")
                return False
            
            # Read metadata to get content type
            metadata_content = {}
            try:
                with open(metadata_file, 'r') as f:
                    metadata_content = json.load(f)
            except Exception as e:
                logger.warning(f"Could not read metadata for content type: {e}")
            
            content_type = metadata_content.get("content_type", "application/octet-stream")
                
            # Create File object with original filename and content type
            with open(actual_file_path, 'rb') as audio_file:
                file_obj = File(
                    content=audio_file,
                    filename=filename,
                    content_type=content_type
                )
                video.audio = file_obj
                
            db.session.commit()
            logger.info(f"Successfully attached audio file to video {video.id} with filename: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error attaching audio file: {str(e)}")
            db.session.rollback()
            return False


def recover_files() -> Dict[str, any]:
    """
    Convenience function for file recovery.
    
    Returns:
        Dict with recovery results
    """
    return FileRecoveryService.recover_files()