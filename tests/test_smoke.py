"""
Smoke tests — the simplest possible checks that the app is alive.

These touch no database: they just confirm the app builds, routes
resolve, and the login page renders. If these pass, the whole pytest
machinery (fixtures, test client, discovery) is working.

Place this file at: tests/test_smoke.py
"""


def test_login_page_loads(client):
    """The login page should return HTTP 200 (OK)."""
    response = client.get('/login')
    assert response.status_code == 200


def test_login_page_has_form(client):
    """The login page should actually contain a login form."""
    response = client.get('/login')
    # response.data is the raw HTML bytes; check the password field is present.
    assert b'password' in response.data
