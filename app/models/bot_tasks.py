"""
Communications between the bot and the main application
"""
import json
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class ClipCreationTask:
    """Task for creating a Twitch clip"""
    broadcaster_id: str
    task_id: Optional[str] = None
    
    def to_json(self) -> str:
        """Convert task to JSON string"""
        return json.dumps({
            "task_type": "create_clip",
            "broadcaster_id": self.broadcaster_id,
            "task_id": self.task_id
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ClipCreationTask':
        """Create task from JSON string"""
        data = json.loads(json_str)
        return cls(
            broadcaster_id=data["broadcaster_id"],
            task_id=data.get("task_id")
        )
