from flask.testing import FlaskClient
from app.models.db import Users

def test_logged_in_client_fixture(logged_in_client: FlaskClient, user: Users):
    """Test that the logged_in_client fixture properly authenticates the user."""
    with logged_in_client as client:
        response = client.get("/")
        assert response.status_code == 200
        assert user.name.encode() in response.data

def test_session_contains_user_id(logged_in_client: FlaskClient, user: Users):
    """Test that the session contains the user ID."""
    with logged_in_client as client:
        with client.session_transaction() as sess:
            assert '_user_id' in sess
            assert int(sess['_user_id']) == user.id

def test_protected_route_access(logged_in_client: FlaskClient):
    """Test that the logged_in_client can access a protected route."""
    with logged_in_client as client:
        response = client.get("/broadcaster")
        assert b"broadcaster" in response.data
        assert response.status_code == 200
