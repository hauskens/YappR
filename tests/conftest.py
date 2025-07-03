import os
import time
import sys
from typing import Generator, Optional
from contextlib import contextmanager

import docker
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from docker.models.containers import Container
from flask import Flask, session
from flask.testing import FlaskClient
from flask_login import login_user
from sqlalchemy.orm import scoped_session, sessionmaker
from testcontainers.postgres import PostgresContainer

# Determine if we're running in unit-test only mode
unit_test_mode = "--unit" in sys.argv or os.environ.get("PYTEST_UNIT_ONLY") == "1"

# Create a unit test marker
pytest.mark.unit = pytest.mark.unit

# pytest_async marker for async tests
try:
    import pytest_asyncio
except ImportError:
    @pytest.fixture
    def event_loop():
        import asyncio
        loop = asyncio.get_event_loop_policy().new_event_loop()
        yield loop
        loop.close()
    
    def asyncio_mark(f):
        return pytest.mark.usefixtures('event_loop')(f)
    
    pytest.mark.asyncio = asyncio_mark

# Import models only if we're not running unit tests
db_required = not unit_test_mode
if db_required:
    from app import create_app
    from app.models.db import db as _db
    from app.models.db import (
        Platforms, Broadcaster, Users, AccountSource, OAuth
    )

    os.environ["TC_REUSE_LOCAL"] = "true"
else:
    # Create mocks for when we're running unit tests only
    # Define minimal versions of types for type annotations
    class MockDB:
        def __init__(self):
            self.session = None
    
    # Create stub classes for type annotations
    class Users: pass
    class OAuth: pass
    class AccountSource:
        Twitch = "Twitch"
        Discord = "Discord"
    class Platforms: pass
    class Broadcaster: pass
    
    _db = MockDB()

def _find_running_container() -> Container | None:
    if not db_required:
        return None
        
    cli = docker.from_env()
    # any container we started earlier and left running?
    try:
        return cli.containers.get('yappr-test-postgres')
    except docker.errors.NotFound:
        return None

@pytest.fixture(scope="session")
def pg_uri() -> Generator[str, None, None]:
    # If we're running unit tests only, yield a dummy string and exit early
    if not db_required:
        yield "sqlite:///:memory:"
        return
        
    reuse = os.getenv("TC_REUSE_LOCAL", "false").lower() == "true"
    if reuse and (ctr := _find_running_container()):
        if ctr.status != "running":
            ctr.start()
            time.sleep(1)
        host, port = ctr.attrs["NetworkSettings"]["IPAddress"], 5432
        yield f"postgresql://test:test@{host}:{port}/test"
        return

    pg = PostgresContainer("pgvector/pgvector:pg17")
    pg.with_env("POSTGRES_PASSWORD", "test").with_name("yappr-test-postgres").start()
    try:
        yield pg.get_connection_url()
    finally:
        if not reuse:
            pg.stop()

@pytest.fixture(scope="session")
def app(pg_uri: str) -> Generator[Flask, None, None]:
    # For unit tests, provide a mock app
    if not db_required:
        class MockApp:
            def __init__(self):
                self.config = {"TESTING": True}
            
            @contextmanager
            def app_context(self):
                yield self
        
        yield MockApp()
        return
    
    # For database-dependent tests, create a real Flask app
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": pg_uri})

    alembic_cfg = AlembicConfig("alembic.ini")
    os.environ["DB_URI"] = pg_uri
    command.upgrade(alembic_cfg, "head")
    yield app

    # drop everything when the test-session ends
    with app.app_context():
        _db.drop_all()


@pytest.fixture(scope="session")
def client(app: Flask) -> FlaskClient:
    # For unit tests, provide a minimal mock client
    if not db_required:
        class MockClient:
            def get(self, *args, **kwargs):
                return None
            def post(self, *args, **kwargs):
                return None
        return MockClient()
    
    # For database tests, return a real test client
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app: Flask) -> Generator[scoped_session, None, None]:
    """
    Creates a brand-new transaction and binds a scoped-session to it.
    Rolls back after the test, so tables stay migrated but data disappears.
    """
    # For unit tests, provide a mock session
    if not db_required:
        class MockSession:
            def add(self, *args, **kwargs): pass
            def add_all(self, *args, **kwargs): pass
            def commit(self, *args, **kwargs): pass
            def flush(self, *args, **kwargs): pass
            def refresh(self, *args, **kwargs): pass
            def execute(self, *args, **kwargs): 
                from unittest.mock import MagicMock
                mock = MagicMock()
                mock.scalars.return_value.one_or_none.return_value = None
                return mock
        
        yield MockSession()
        return
    
    # For database tests, set up a real session with transaction
    ctx = app.app_context()
    ctx.push()
    connection = _db.engine.connect()
    txn = connection.begin()

    SessionFactory = sessionmaker(bind=connection, expire_on_commit=False)
    session = scoped_session(SessionFactory)
    # Monkey-patch the global `db.session` so model code in the app
    # continues to use `db.session.<…>` but is now isolated to this test.
    _orig_session_prop = _db.session      # keep a reference to restore later
    _db.session = session                 # shadow the read-only property

    try:
        yield session
    finally:
        # ── clean up ──────────────────────────────────────────────────────────
        session.remove()                 # close the scoped-session
        txn.rollback()                   # discard everything written
        connection.close()
        _db.session = _orig_session_prop  # restore original property
        ctx.pop()

# Skip this autouse fixture if running unit tests only
@pytest.fixture(autouse=(not db_required))
def seed_common_data(db_session: scoped_session) -> Generator[None, None, None]:
    """Populate 'Twitch' and 'YouTube' once per test, then roll back."""
    if not db_required:
        yield
        return
        
    twitch = Platforms(name="Twitch", url="https://twitch.tv", logo_url="https://brand.twitch.tv/assets/images/black.png", color="#6441A4")
    youtube = Platforms(name="YouTube", url="https://youtube.com", logo_url="https://www.youtube.com/s/desktop/12d6b690/img/favicon_144x144.png", color="#FF0000")
    db_session.add_all([twitch, youtube])
    db_session.flush()       # keeps IDs available if other objects depend on them
    broadcaster = Broadcaster(name="TestBroadcaster")
    db_session.add(broadcaster)
    db_session.flush()
    yield 

@pytest.fixture(scope="function")
def user(db_session: scoped_session) -> Users:
    """A fresh user row in the per-test transaction."""
    if not db_required:
        # Return a mock user for unit tests
        from unittest.mock import MagicMock
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.name = "tester"
        mock_user.account_type = "Twitch"
        mock_user.external_account_id = "123456789"
        return mock_user
        
    u = Users(name="tester", account_type=AccountSource.Twitch, external_account_id="123456789")
    db_session.add(u)
    db_session.flush()          # so u.id is available
    return u

@pytest.fixture(scope="function")
def oauth_token(db_session: scoped_session, user: Users) -> OAuth:
    """Create an OAuth token for the test user."""
    if not db_required:
        # Return a mock token for unit tests
        from unittest.mock import MagicMock
        mock_token = MagicMock()
        mock_token.provider = "twitch"
        mock_token.provider_user_id = user.external_account_id
        mock_token.token = {"access_token": "fake_token", "refresh_token": "fake_refresh_token"}
        mock_token.user = user
        return mock_token
        
    oauth = OAuth(
        provider="twitch",
        provider_user_id=user.external_account_id,
        token={"access_token": "fake_token", "refresh_token": "fake_refresh_token"},
        user=user
    )
    db_session.add(oauth)
    db_session.flush()
    return oauth

@pytest.fixture(scope="function")
def logged_in_client(client: FlaskClient, app: Flask, user: Users, oauth_token: OAuth) -> FlaskClient:
    """A test client with an authenticated user session.
    
    This fixture creates a test client with a logged-in user session,
    allowing tests to access routes that require authentication.
    """
    if not db_required:
        # For unit tests, return the mock client directly
        return client
        
    # For DB tests, create a proper authenticated session
    with client.session_transaction() as sess:  # type: Any
        # Set up the Flask-Login session
        with app.test_request_context():
            login_user(user)
            # Transfer the Flask session to the test client session
            for key, value in dict(session).items():
                sess[key] = value
    
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
