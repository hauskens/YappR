from googleapiclient.discovery import build
from models.config import config
from models.youtube.channel import ChannelResourceResponse, ChannelItem
from models.youtube.playlist import PlaylistResourceResponse, PlaylistItem

if config.youtube_api_key is None:
    raise ValueError("YOUTUBE_API_KEY not configured!")
youtube = build("youtube", "v3", developerKey=config.youtube_api_key)


def get_youtube_channel_details(channel_tag: str) -> ChannelItem:
    request = youtube.channels().list(part="id,snippet", forHandle=channel_tag)
    resp = request.execute()
    youtube_channels = ChannelResourceResponse.model_validate(resp)
    return youtube_channels.items.pop(0)


def get_youtube_playlist_details(channel_id: str) -> list[PlaylistItem]:
    request = youtube.playlists().list(
        part="snippet,contentDetails", channelId=channel_id, maxResults=25
    )
    resp = request.execute()
    playlists = PlaylistResourceResponse.model_validate(resp)
    return playlists.items


if __name__ == "__main__":
    # channel = get_youtube_channel_details("@HistoryoftheUniverse")
    playlists = get_youtube_playlist_details("UCtRFmSyL4fSLQkn-wMqlmdA")
    for p in playlists:
        print(p.snippet.title)
