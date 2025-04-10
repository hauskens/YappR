from googleapiclient.discovery import build
from .models.config import config
from .models.youtube import ChannelResourceListResponse, ChannelItem

if config.youtube_api_key is None:
    raise ValueError("YOUTUBE_API_KEY not configured!")
youtube = build("youtube", "v3", developerKey=config.youtube_api_key)


def get_youtube_channel_details(channel_tag: str) -> ChannelItem:
    request = youtube.channels().list(part="id,snippet", forHandle=channel_tag)
    resp = request.execute()
    youtube_channels = ChannelResourceListResponse.model_validate(resp)
    return youtube_channels.items.pop(0)


if __name__ == "__main__":
    channel = get_youtube_channel_details("@HistoryoftheUniverse")
    print(channel.snippet.title)
