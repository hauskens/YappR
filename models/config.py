import os


class Config:
    def __init__(self):
        self.app_secret: str = os.environ.get("APP_SECRET", "omgtesties")
        self.database_uri: str = os.environ.get("DB_URI", "sqlite:///project.db")
