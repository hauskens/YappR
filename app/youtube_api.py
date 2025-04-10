from googleapiclient.discovery import build
from models.config import config
from models.youtube.channel import ChannelResourceResponse, ChannelItem
from models.youtube.playlist import PlaylistResourceResponse, PlaylistItem
from models.youtube.search import SearchResourceResponse, SearchResultItem

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


def get_youtube_search(channel_id: str) -> list[SearchResultItem]:
    request = youtube.search().list(
        part="snippet", type="video", channelId=channel_id, maxResults=25
    )
    resp = request.execute()
    videos = SearchResourceResponse.model_validate(resp)
    return videos.items


if __name__ == "__main__":
    # channel = get_youtube_channel_details("@HistoryoftheUniverse")
    # playlists = get_youtube_playlist_details("UCtRFmSyL4fSLQkn-wMqlmdA")
    videos = get_youtube_search("UCtRFmSyL4fSLQkn-wMqlmdA")
    for p in videos:
        print(p.snippet.title)
