import os
import logging
from dotenv import load_dotenv


class Config:
    def __init__(self):
        self.app_secret: str = os.environ.get(
            "APP_SECRET", "ajsdlfknsdkfjnsdafiouswe")
        self.app_url: str = os.environ.get("APP_URL", "http://127.0.0.1:5000")
        self.database_uri: str = os.environ.get(
            "DB_URI",
            "postgresql+psycopg://postgres:mysecretpassword@postgres-db:5432/postgres",
        )
        self.log_level: str | int = os.environ.get("LOG_LEVEL", logging.DEBUG)
        self.debug: bool = os.environ.get("DEBUG", "").lower() == "true"
        self.debug_broadcaster_id: int | None = os.environ.get(
            "DEBUG_BROADCASTER_ID")
        self.storage_location: str = os.environ.get(
            "STORAGE_LOCATION", "/var/lib/yappr/data"
        )
        self.cache_location: str = os.environ.get(
            "CACHE_LOCATION", "/var/lib/yappr/cache"
        )
        self.redis_uri: str = os.environ.get(
            "REDIS_URI", "redis://redis-cache:6379/0")
        self.app_port: int = int(os.environ.get("PORT", 5000))
        self.app_host: str = os.environ.get("HOST", "0.0.0.0")
        self.nltk_data: str = os.environ.get(
            "NLTK_DATA", "/var/lib/yappr/nltk"
        )  # Todo: this does not do anything yet
        self.discord_client_id: str | None = os.environ.get(
            "DISCORD_CLIENT_ID")
        self.discord_client_secret: str | None = os.environ.get(
            "DISCORD_CLIENT_SECRET")
        self.discord_redirect_uri: str | None = os.environ.get(
            "DISCORD_REDIRECT_URI")
        self.youtube_api_key: str | None = os.environ.get("YOUTUBE_API_KEY")
        self.webshare_proxy_username: str | None = os.environ.get(
            "WEBSHARE_PROXY_USERNAME"
        )
        self.webshare_proxy_password: str | None = os.environ.get(
            "WEBSHARE_PROXY_PASSWORD"
        )
        self.twitch_client_id: str = os.environ.get("TWITCH_CLIENT_ID")
        self.twitch_client_secret: str = os.environ.get(
            "TWITCH_CLIENT_SECRET")
        self.twitch_dl_gql_client_id: str | None = os.environ.get(
            "TWITCH_DL_GQL_CLIENT_ID"
        )
        self.transcription_device: str = os.environ.get(
            "TRANSCRIPTION_DEVICE", "cpu")
        self.transcription_model: str = os.environ.get(
            "TRANSCRIPTION_MODEL", "large-v2"
        )
        self.transcription_compute_type: str = os.environ.get(
            "TRANSCRIPTION_COMPUTE_TYPE", "float16"
        )  # for cpu, use int8
        self.transcription_batch_size: int = int(
            os.environ.get("TRANSCRIPTION_BATCH_SIZE", 8)
        )  # lower this if gpu vram low
        self.api_key: str = os.environ.get("API_KEY", "not_a_secure_key!11")
        self.hf_token: str | None = os.environ.get("HF_TOKEN")
        self.discord_bot_token: str | None = os.environ.get(
            "DISCORD_BOT_TOKEN")
        self.bot_discord_enabled: bool = os.environ.get(
            "BOT_DISCORD_ENABLED", "false").lower() == "true"
        self.bot_discord_admin_guild: int = os.environ.get(
            "BOT_DISCORD_ADMIN_GUILD")
        self.bot_twitch_enabled: bool = os.environ.get(
            "BOT_TWITCH_ENABLED", "false").lower() == "true"
        self.environment: str = os.environ.get("ENVIRONMENT", "development")
        self.service_name: str = os.environ.get("SERVICE_NAME", "app")
        # example: http://localhost:4040/loki/api/v1/push
        self.loki_url: str | None = os.environ.get("LOKI_URL")
        self.timezone: str = os.environ.get("TIMEZONE", "Europe/Oslo")
        self.version: str = os.environ.get("VERSION", "0.0.0")
        self.default_cache_time: int = int(os.environ.get("DEFAULT_CACHE_TIME", 300))


_ = load_dotenv()
config = Config()
