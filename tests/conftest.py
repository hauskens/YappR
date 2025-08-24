from typing import Generator
from contextlib import contextmanager
from unittest.mock import Mock, MagicMock, patch
from app.models.user import UserBase
from app.models.enums import AccountSource
from datetime import datetime
import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.orm import scoped_session
from pydantic import ConfigDict
import os

# Create mocks for database-dependent imports
class MockDB:
    def __init__(self):
        self.session = None

class MockUsers:
    def __init__(self, name="tester", account_type="Twitch", external_account_id="123456789"):
        self.id = 1
        self.name = name
        self.account_type = account_type
        self.external_account_id = external_account_id
        self.is_anonymous = False
        self.is_authenticated = True

class MockOAuth:
    def __init__(self, provider="twitch", provider_user_id="123456789", token=None, user=None):
        self.provider = provider
        self.provider_user_id = provider_user_id
        self.token = token or {"access_token": "fake_token", "refresh_token": "fake_refresh_token"}
        self.user = user

_db = MockDB()
Users = MockUsers
OAuth = MockOAuth


@contextmanager
def patch_database_dependencies():
    """Patch all database-related dependencies for testing."""
    patches = [
        # Mock database models and operations
        patch('app.models.db.init_app'),
        patch('app.models.db.create_all'),
        patch('app.models.db.drop_all'),
        patch('app.models.db.session', new_callable=lambda: create_mock_db_session()),
        
        # Mock Flask-Login user loader
        patch('app.app_factory.load_user', side_effect=create_mock_user_loader()),
        
        # Mock services that use database
        patch('app.services.BroadcasterService.get_all', return_value=create_mock_broadcasters()),
        patch('app.services.UserService.get_all', return_value=[]),
        
        # Mock authentication-related components
        patch('app.models.auth.OAuth'),
        patch('app.models.user.Users'),
        
        # Mock storage and external dependencies
        patch('app.app_factory.init_storage'),
        patch('app.app_factory.StorageManager'),
        patch('app.redis_client.RedisTaskQueue'),
        
        # Mock cache
        patch('app.cache.cache.init_app'),
    ]
    
    # Start all patches
    mocks = [p.start() for p in patches]
    
    try:
        yield mocks
    finally:
        # Stop all patches
        for p in patches:
            p.stop()


def create_mock_db_session():
    """Create a mock database session."""
    mock_session = MagicMock()
    
    # Create a mock OAuth object that returns a user
    mock_oauth = MagicMock()
    mock_oauth.user = create_mock_user()
    
    # Mock query methods - return OAuth object for user loader
    mock_session.query.return_value.filter_by.return_value.one.return_value = mock_oauth
    mock_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_oauth
    mock_session.query.return_value.filter_by.return_value.first.return_value = mock_oauth
    mock_session.query.return_value.filter_by.return_value.all.return_value = []
    
    # Mock transaction methods
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    mock_session.flush = MagicMock()
    
    return mock_session


def create_mock_broadcasters():
    """Create mock broadcaster objects for testing."""
    class MockBroadcaster:
        def __init__(self, id, name, hidden=False):
            self.id = id
            self.name = name
            self.hidden = hidden
    
    return [MockBroadcaster(1, "TestBroadcaster", False)]

def create_mock_user():
    class MockUser(UserBase):
        model_config = ConfigDict(extra="allow")
        
        @property
        def is_anonymous(self):
            return False
        
        @property
        def is_authenticated(self):
            return True
        
        @property 
        def is_active(self):
            return True
        
        def get_id(self):
            return str(self.id)
    
    user = MockUser(
        id=1,
        name="tester",
        external_account_id="123456789",
        account_type=AccountSource.Twitch,
        first_login=datetime.now(),
        last_login=datetime.now(),
        avatar_url="https://example.com/avatar.jpg",
        broadcaster_id=1,
        banned=False,
        banned_reason=None
    )
    # Add permissions attribute for template compatibility
    user.permissions = []
    return user


def create_mock_user_loader():
    """Create a mock user loader function."""
    # Store logged in users globally for the test session
    _logged_in_users = {"123456789": create_mock_user()}

    
    def mock_load_user(oauth_id):
        return _logged_in_users.get(oauth_id)
    
    # Allow setting users from fixtures
    mock_load_user._logged_in_users = _logged_in_users
    return mock_load_user

@pytest.fixture(scope="session", autouse=True)
def set_test_environment():
    os.environ["TESTING"] = "1"
    yield
    os.environ.pop("TESTING", None)

@pytest.fixture(scope="session")
def pg_uri() -> Generator[str, None, None]:
    yield "sqlite:///:memory:"

@pytest.fixture(scope="session")
def app(pg_uri: str) -> Generator[Flask, None, None]:
    # Create a real Flask app but mock all database interactions
    with patch_database_dependencies():
        from app.app_factory import create_app
        app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
        yield app


@pytest.fixture(scope="session")
def client(app: Flask) -> FlaskClient:
    # Return a real test client with the mocked app
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app: Flask) -> Generator[scoped_session, None, None]:
    """
    Provides a mock session for testing without database.
    """
    yield create_mock_db_session()


@pytest.fixture(scope="function")
def user(db_session: scoped_session) -> Users:
    """A mock user for testing."""
    return Users(name="tester", account_type="Twitch", external_account_id="123456789")

@pytest.fixture(scope="function")
def oauth_token(db_session: scoped_session, user: Users) -> OAuth:
    """Create a mock OAuth token for the test user."""
    return OAuth(
        provider="twitch",
        provider_user_id=user.external_account_id,
        token={"access_token": "fake_token", "refresh_token": "fake_refresh_token"},
        user=user
    )

@pytest.fixture(scope="function")
def logged_in_client(client: FlaskClient, app: Flask, user: Users, oauth_token: OAuth) -> FlaskClient:
    """A test client with an authenticated user session.
    
    This fixture creates a test client with a logged-in user session,
    allowing tests to access routes that require authentication.
    """
    # Add the user to the mock user loader
    if hasattr(app, 'login_manager') and hasattr(app.login_manager, '_user_callback'):
        if hasattr(app.login_manager._user_callback, '_logged_in_users'):
            app.login_manager._user_callback._logged_in_users[str(user.id)] = user
    
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
    
    return client


# Add a pytest helper to allow running fast unit tests only
def pytest_addoption(parser):
    parser.addoption(
        "--unit",
        action="store_true",
        default=False,
        help="Run only unit tests that don't need database setup"
    )
    
# Add a marker for unit tests that don't need DB
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "unit: mark test as a unit test that doesn't need database/app setup"
    )
    config.addinivalue_line(
        "markers", 
        "asyncio: mark test as an async test"
    )