import os
import logging


class Config:
    def __init__(self):
        self.app_secret: str = os.environ.get("APP_SECRET", "omgtesties")
        self.database_uri: str = os.environ.get(
            "DB_URI",
            "postgresql+psycopg://postgres:mysecretpassword@localhost:5432/postgres",
        )
        self.log_level: str | int = os.environ.get("LOG_LEVEL", logging.DEBUG)
        self.storage_location: str = os.environ.get(
            "STORAGE_LOCATION", "./test_storage"
        )
        self.redis_uri: str = os.environ.get("REDIS_URI", "redis://localhost:6379/0")
        self.app_port: int = int(os.environ.get("PORT", 5000))
        self.app_host: str = os.environ.get("HOST", "0.0.0.0")
