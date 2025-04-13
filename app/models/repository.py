from pydantic import BaseModel
from .db import db, Channels
from ..youtube_api import get_youtube_channel_details
from sqlalchemy.orm import Query


class Channel:
    db_ref: Channels

    def __init__(self, channel_id: int):
        self.db_ref = db.session.query(Channels).filter_by(id=channel_id).one()

    def get(self) -> Channels:
        return self.db_ref

    def update(self):
        result = get_youtube_channel_details(self.db_ref.platform_ref)
        self.db_ref.platform_channel_id = result.id
        db.session.commit()

    def delete(self):
        _ = db.session.query(Channels).filter_by(id=self.db_ref.id).delete()
        db.session.commit()
