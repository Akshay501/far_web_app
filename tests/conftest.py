"""
Shared pytest fixtures for the FAR web app.

pytest automatically discovers fixtures in conftest.py and makes them
available to every test file in this folder — no import needed.

Place this file at: tests/conftest.py
"""
import pytest
from app import create_app


@pytest.fixture
def app():
    """Build a Flask app instance configured for testing."""
    app = create_app()
    # TESTING mode gives clearer errors and better test behavior.
    app.config['TESTING'] = True
    # Turn OFF CSRF protection during tests so we can POST to forms
    # (login, generate) without needing a real CSRF token. This is a
    # test-only relaxation; production still has CSRF fully enabled.
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app):
    """A test client that can send fake requests to the app in memory."""
    return app.test_client()
