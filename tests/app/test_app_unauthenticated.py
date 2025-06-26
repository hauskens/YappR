from flask.testing import FlaskClient

def test_front_page_loads_unauthenticated(client: FlaskClient):
    """Test that the front page loads successfully when unauthenticated."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.request.path == "/"
    
def test_search_page_loads_unauthenticated(client: FlaskClient):
    """Test that the search page loads successfully when unauthenticated."""
    response = client.get("/search")
    assert response.status_code == 200
    assert b"Search..." in response.data
    assert response.request.path == "/search"

def test_login_page(client: FlaskClient):
    """Test that the /login page loads and displays the welcome page"""
    # First check the login page
    with client:
        response = client.get("/login")
        assert response.status_code == 200
        assert response.request.path == "/login"
        assert b"Welcome to YappR!" in response.data

def test_unauthenticated_user_cannot_access_protected_routes(client: FlaskClient):
    """Test that unauthenticated users cannot access protected routes."""
    protected_routes = ["/broadcaster", "/management", "/users" ]
    for route in protected_routes:
        response = client.get(route)
        assert response.status_code in (302, 308, 401)