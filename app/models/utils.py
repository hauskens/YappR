from pydantic import BaseModel
from typing import Callable, Dict, Any


class DownloadProgress(BaseModel):
    """
    Pydantic model representing the download progress information
    used in yt-dlp progress hooks.
    """
    current: int  # Downloaded bytes
    total: int    # Total bytes
    percent: float  # Download percentage
    speed: float  # Download speed in bytes/s
    eta: int      # Estimated time of arrival in seconds
    status: str   # Status message

    class Config:
        arbitrary_types_allowed = True


# Type for the progress callback function
ProgressCallbackType = Callable[[Dict[str, Any]], None]
