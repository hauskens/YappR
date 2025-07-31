from pydantic import BaseModel, ConfigDict
from typing import Callable, Dict, Any


class DownloadProgress(BaseModel):
    """
    Pydantic model representing the download progress information
    used in yt-dlp progress hooks.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    current: int | None  # Downloaded bytes
    total: float | None    # Total bytes
    percent: float | None  # Download percentage
    speed: float = 0  # Download speed in bytes/s
    eta: float | None = None  # Estimated time of arrival in seconds
    status: str | None   # Status message


# Type for the progress callback function
ProgressCallbackType = Callable[[Dict[str, Any]], None]
