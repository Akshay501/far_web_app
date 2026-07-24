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


# A known publication to edit in tests. Two authors, neither marked.
TEST_PUBLICATION_KEY = 9001
TEST_BIBKEY = 'PytestSample2025'

TEST_RAW_BIBTEX = """@article{PytestSample2025,
  author = {Alice Smith and Bob Jones},
  title = {A Sample Publication For Testing},
  journal = {Journal of Testing},
  year = {2025},
  keywords = {journal}
}"""


@pytest.fixture
def logged_in_client(client, seed_professor):
    """A test client that has already logged in as the seeded professor."""
    client.post('/login', data={
        'email': seed_professor['email'],
        'password': seed_professor['password'],
    })
    return client


@pytest.fixture
def scaffold(tmp_path, app):
    """A miniature scaffold template + empty professors root in a temp
    dir, with app config pointed at them — shared by every test that
    exercises folder creation (folder service, registration, admin
    creation, self-healing).

    Mirrors the real template's shape: PersonalData placeholders,
    stats-enabled cfg files (with a non-stats key that must survive
    patching), a .git dir that must NOT be copied, and a data file that
    must be copied verbatim."""
    tpl = tmp_path / 'template'
    (tpl / 'make_cv' / 'PersonalData').mkdir(parents=True)
    (tpl / 'make_cv' / 'FAR').mkdir(parents=True)
    (tpl / 'make_cv' / 'CV').mkdir(parents=True)
    (tpl / 'Scholarship').mkdir()
    (tpl / '.git').mkdir()

    (tpl / '.git' / 'HEAD').write_text('ref: refs/heads/main\n')
    (tpl / 'Scholarship' / 'scholarship.bib').write_text('% template bib\n')
    (tpl / 'make_cv' / 'PersonalData' / 'personal_data.txt').write_text(
        '# Personal data (IDs) for make_cv\n'
        'googleid = \n'
        'webscraperid = \n'
        'scopusid = \n'
        'orcid = \n'
    )
    (tpl / 'make_cv' / 'PersonalData' / 'ContactInfo.tex').write_text(
        '\\mynames{Doe/J}\n'
        '\\leftheader{{\\LARGE Jane U.\\ Doe, Ph.D.}\\\\\n'
        'Somewhere University, Somewhere, XX 16753\\\\\n'
        'myemail@somewhere.edu}\n'
    )
    for sub in ('FAR', 'CV'):
        (tpl / 'make_cv' / sub / 'make_cv.cfg').write_text(
            '[CV]\n'
            'years = 1\n'
            'googlestats = true\n'
            'scopusstats = true\n'
        )

    root = tmp_path / 'Professors'
    root.mkdir()

    app.config['SCAFFOLD_TEMPLATE'] = str(tpl)
    app.config['PROFESSORS_ROOT'] = str(root)
    app.config['INSTITUTION'] = {
        'name': 'Clarkson University',
        'address': '8 Clarkson Ave, Potsdam, NY 13699',
        'email_domain': 'clarkson.edu',
    }
    app.config['DEPARTMENTS'] = [
        'Electrical and Computer Engineering',
        'Computer Science',
    ]
    return {'template': tpl, 'root': root}


@pytest.fixture
def seed_publication(app, seed_professor):
    """Insert one known publication owned by the seeded professor."""
    with app.app_context():
        assert app.config['DB_CONFIG']['db'] == TEST_DB_NAME

        execute_query('DELETE FROM PUBLICATIONS WHERE PublicationKey=%s',
                      (TEST_PUBLICATION_KEY,), commit=True)

        execute_query(
            'INSERT INTO PUBLICATIONS '
            '(PublicationKey, ProfessorKey, BibKey, Type, Title, Authors, '
            ' Year, Journal, Keywords, RawBibtex) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (TEST_PUBLICATION_KEY, seed_professor['professor_key'],
             TEST_BIBKEY, 'article', 'A Sample Publication For Testing',
             'Alice Smith and Bob Jones', 2025, 'Journal of Testing',
             'journal', TEST_RAW_BIBTEX),
            commit=True
        )

    yield {
        'id': TEST_PUBLICATION_KEY,
        'bibkey': TEST_BIBKEY,
    }

    with app.app_context():
        assert app.config['DB_CONFIG']['db'] == TEST_DB_NAME
        execute_query('DELETE FROM PUBLICATIONS WHERE PublicationKey=%s',
                      (TEST_PUBLICATION_KEY,), commit=True)
