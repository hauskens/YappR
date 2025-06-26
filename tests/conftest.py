import os
import time
from typing import Generator

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

from app import create_app
from app.models.db import db as _db
from app.models.db import (
    Platforms, Broadcaster, Users, AccountSource, OAuth
)

os.environ["TC_REUSE_LOCAL"] = "true"

def _find_running_container() -> Container | None:
    cli = docker.from_env()
    # any container we started earlier and left running?
    try:
        return cli.containers.get('yappr-test-postgres')
    except docker.errors.NotFound:
        return None

@pytest.fixture(scope="session")
def pg_uri() -> Generator[str, None, None]:
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
    return app.test_client()

@pytest.fixture(scope="function")
def db_session(app: Flask) -> Generator[scoped_session, None, None]:
    """
    Creates a brand-new transaction and binds a scoped-session to it.
    Rolls back after the test, so tables stay migrated but data disappears.
    """
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

@pytest.fixture(autouse=True)
def seed_common_data(db_session: scoped_session) -> Generator[None, None, None]:
    """Populate 'Twitch' and 'YouTube' once per test, then roll back."""
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
    u = Users(name="tester", account_type=AccountSource.Twitch, external_account_id="123456789")
    db_session.add(u)
    db_session.flush()          # so u.id is available
    return u

@pytest.fixture(scope="function")
def oauth_token(db_session: scoped_session, user: Users) -> OAuth:
    """Create an OAuth token for the test user."""
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
    with client.session_transaction() as sess:  # type: Any
        # Set up the Flask-Login session
        with app.test_request_context():
            login_user(user)
            # Transfer the Flask session to the test client session
            for key, value in dict(session).items():
                sess[key] = value
    
    return client
