"""
Authentication tests — the first tests that touch the database.

These run against thuguda_FAR_test (see conftest.py), using a seeded
professor account, so they never read or write real data.

Place this file at: tests/test_auth.py
"""


def test_login_succeeds_and_redirects(client, seed_professor):
    """Valid credentials should log in and redirect to the dashboard."""
    response = client.post('/login', data={
        'email': seed_professor['email'],
        'password': seed_professor['password'],
    })
    # 302 = redirect, which is what a successful login returns.
    assert response.status_code == 302
    assert '/professor/dashboard' in response.headers['Location']


def test_login_fails_with_wrong_password(client, seed_professor):
    """A bad password should NOT log in — the page re-renders instead."""
    response = client.post('/login', data={
        'email': seed_professor['email'],
        'password': 'definitely-not-the-password',
    })
    # No redirect: we stay on the login page (200), not sent to a dashboard.
    assert response.status_code == 200


def test_dashboard_requires_login(client):
    """Visiting the dashboard while logged out should redirect to login."""
    response = client.get('/professor/dashboard')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
