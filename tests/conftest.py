"""
Shared pytest fixtures for the FAR web app.

IMPORTANT: every fixture here points the app at the TEST database
(thuguda_FAR_test), never the real one. There is a hard safety check
below that refuses to run if that override didn't take effect.

Place this file at: tests/conftest.py
"""
import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.utils import execute_query

# The test sandbox database. Must NOT be the real 'thuguda_FAR'.
TEST_DB_NAME = 'thuguda_FAR_test'

# Known seed values the tests log in with.
TEST_EMAIL = 'pytest.professor@clarkson.edu'
TEST_PASSWORD = 'pytest123'
TEST_PROFESSOR_KEY = 9001      # high number, won't collide with real keys
TEST_USER_ID = 9001


@pytest.fixture
def app():
    """Flask app wired to the TEST database, with CSRF off for testing."""
    app = create_app()
    app.config['TESTING'] = True
    # Turn off CSRF so tests can POST forms without a real token.
    app.config['WTF_CSRF_ENABLED'] = False

    # ---- Point every query at the test database -------------------------
    # execute_query reads current_app.config['DB_CONFIG'] on each call,
    # so swapping the db name here reroutes the whole app to the sandbox.
    db_cfg = dict(app.config['DB_CONFIG'])   # copy, don't mutate the original
    db_cfg['db'] = TEST_DB_NAME
    app.config['DB_CONFIG'] = db_cfg

    # ---- Safety net -----------------------------------------------------
    # If the override ever fails, stop immediately rather than letting a
    # test write to the real database.
    assert app.config['DB_CONFIG']['db'] == TEST_DB_NAME, \
        'Refusing to run: tests are not pointed at the test database!'

    return app


@pytest.fixture
def client(app):
    """A test client that sends fake requests to the app in memory."""
    return app.test_client()


@pytest.fixture
def seed_professor(app):
    """
    Insert a known professor + user into the TEST database, then remove
    them afterwards so every test starts from the same clean state.
    """
    with app.app_context():
        # Extra guard: never touch anything unless we're on the test DB.
        assert app.config['DB_CONFIG']['db'] == TEST_DB_NAME

        # Clean up any leftovers from a previous interrupted run.
        execute_query('DELETE FROM users WHERE UserID=%s', (TEST_USER_ID,), commit=True)
        execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey=%s',
                      (TEST_PROFESSOR_KEY,), commit=True)

        execute_query(
            'INSERT INTO PROFESSOR (ProfessorKey, FirstName, LastName, Department) '
            'VALUES (%s, %s, %s, %s)',
            (TEST_PROFESSOR_KEY, 'Pytest', 'Professor', 'Aerospace Engineering'),
            commit=True
        )
        execute_query(
            'INSERT INTO users (UserID, Name, Email, Password, Role, ProfessorKey) '
            'VALUES (%s, %s, %s, %s, %s, %s)',
            (TEST_USER_ID, 'Pytest Professor', TEST_EMAIL,
             generate_password_hash(TEST_PASSWORD), 'professor',
             TEST_PROFESSOR_KEY),
            commit=True
        )

    yield {
        'email': TEST_EMAIL,
        'password': TEST_PASSWORD,
        'professor_key': TEST_PROFESSOR_KEY,
        'user_id': TEST_USER_ID,
    }

    # ---- teardown: remove the seed rows --------------------------------
    with app.app_context():
        assert app.config['DB_CONFIG']['db'] == TEST_DB_NAME
        execute_query('DELETE FROM users WHERE UserID=%s', (TEST_USER_ID,), commit=True)
        execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey=%s',
                      (TEST_PROFESSOR_KEY,), commit=True)
