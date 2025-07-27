import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.broadcaster import Broadcaster, BroadcasterSettings
from app.models.user import Users
from app.models.platform import Platforms

class TestModelsIntegration:
    """Integration tests that require database connections."""
    
    def test_broadcaster_creation(self, db_session):
        """Test creating a broadcaster."""
        broadcaster = Broadcaster(name="test_broadcaster")
        db_session.add(broadcaster)
        db_session.commit()
        
        assert broadcaster.id is not None
        assert broadcaster.name == "test_broadcaster"
        assert broadcaster.hidden is False
    
    def test_broadcaster_settings_relationship(self, db_session):
        """Test broadcaster settings relationship."""
        broadcaster = Broadcaster(name="test_broadcaster")
        db_session.add(broadcaster)
        db_session.flush()  # Get ID
        
        settings = BroadcasterSettings(
            broadcaster_id=broadcaster.id,
            linked_discord_channel_verified=True
        )
        db_session.add(settings)
        db_session.commit()
        
        assert settings.broadcaster_id == broadcaster.id
        assert settings.linked_discord_channel_verified is True
    
    def test_broadcaster_unique_name(self, db_session):
        """Test that broadcaster names must be unique."""
        broadcaster1 = Broadcaster(name="duplicate_name")
        broadcaster2 = Broadcaster(name="duplicate_name")
        
        db_session.add(broadcaster1)
        db_session.commit()
        
        db_session.add(broadcaster2)
        
        with pytest.raises(Exception):  # Should raise integrity error
            db_session.commit()