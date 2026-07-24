"""
Tests for student-award ownership and scoping (repair of the unscoped
student-awards feature).

Written BEFORE the fix. Against the current code these should all be RED:

  - the add path errors (its INSERT references columns that don't exist)
  - the listing shows other professors' awards
  - the export drops the professor's own awards (the join-via-
    PERSONALAWARDS workaround only returns awards that happen to share a
    key with a personal award)
  - delete / duplicate / edit accept any award id, regardless of owner

The contract they define:

  - adding a student award writes an AWARDS parent + a STUDENTAWARDS
    child carrying the logged-in professor's ProfessorKey
  - the listing and the export return only the professor's own awards
  - mutating (edit / delete / duplicate) someone else's award is refused
    and changes nothing

These are integration tests against the TEST database; every row they
create is removed afterwards.
"""
import pytest

from app.utils import execute_query

FOREIGN_PK = 9002          # a professor key that is not the seeded 9001

OWN_TITLE = 'Own Student Award PLUGH'
FOREIGN_TITLE = 'Foreign Student Award XYZZY'
FORM_TITLE = 'Added Via Form QWERTY'


def _insert_award(app, professor_key, title, student='Some Student',
                  amount=100, category='Research', award_type='Graduate',
                  year=2025):
    """Seed a properly-owned award pair (AWARDS parent + STUDENTAWARDS
    child) directly, returning the Award Key."""
    with app.app_context():
        key = execute_query(
            'INSERT INTO AWARDS (Title, Year, `Award Type`) '
            'VALUES (%s, %s, %s)',
            (title, year, award_type), commit=True, lastrowid=True)
        execute_query(
            'INSERT INTO STUDENTAWARDS '
            '(`Award Key`, ProfessorKey, Student, Amount, Category) '
            'VALUES (%s, %s, %s, %s, %s)',
            (key, professor_key, student, amount, category), commit=True)
        return key


@pytest.fixture
def clean_awards(app):
    """After each test, remove every award row the tests may have created
    (looked up by the distinctive titles, child rows first)."""
    yield
    with app.app_context():
        for title in (OWN_TITLE, FOREIGN_TITLE, FORM_TITLE):
            rows = execute_query(
                'SELECT `Award Key` FROM AWARDS WHERE Title = %s', (title,))
            for r in rows:
                execute_query(
                    'DELETE FROM STUDENTAWARDS WHERE `Award Key` = %s',
                    (r['Award Key'],), commit=True)
                execute_query(
                    'DELETE FROM AWARDS WHERE `Award Key` = %s',
                    (r['Award Key'],), commit=True)


# ------------------------------------------------------------------- add

def test_add_student_award_creates_owned_rows(app, logged_in_client,
                                              seed_professor, clean_awards):
    resp = logged_in_client.post('/professor/awards', data={
        'form_type': 'student',
        'student_name': 'Form Student',
        'award_title': FORM_TITLE,
        'amount': '150.00',
        'category': 'Research',
        'type': 'Graduate',
        'year': '2025',
    })
    assert resp.status_code in (200, 302)

    with app.app_context():
        parent = execute_query(
            'SELECT * FROM AWARDS WHERE Title = %s',
            (FORM_TITLE,), fetchone=True)
        assert parent is not None, 'AWARDS parent row should exist'
        assert parent['Year'] == 2025

        child = execute_query(
            'SELECT * FROM STUDENTAWARDS WHERE `Award Key` = %s',
            (parent['Award Key'],), fetchone=True)
        assert child is not None, 'STUDENTAWARDS child row should exist'
        assert child['ProfessorKey'] == seed_professor['professor_key']
        assert child['Student'] == 'Form Student'


# --------------------------------------------------------------- listing

def test_listing_shows_only_own_awards(app, logged_in_client,
                                       seed_professor, clean_awards):
    _insert_award(app, seed_professor['professor_key'], OWN_TITLE)
    _insert_award(app, FOREIGN_PK, FOREIGN_TITLE)

    resp = logged_in_client.get('/professor/awards')

    assert resp.status_code == 200
    assert OWN_TITLE.encode() in resp.data
    assert FOREIGN_TITLE.encode() not in resp.data


# ---------------------------------------------------------------- export

def test_export_data_is_scoped_and_direct(app, seed_professor,
                                          clean_awards):
    from app.routes.generate import fetch_all_db_data

    _insert_award(app, seed_professor['professor_key'], OWN_TITLE)
    _insert_award(app, FOREIGN_PK, FOREIGN_TITLE)

    with app.app_context():
        data = fetch_all_db_data(seed_professor['professor_key'])

    titles = [r['Title'] for r in data['student_awards']]
    assert OWN_TITLE in titles, \
        'the professor\'s own award must reach the export'
    assert FOREIGN_TITLE not in titles


# ------------------------------------------------- write-side ownership

def test_cannot_delete_foreign_award(app, logged_in_client,
                                     seed_professor, clean_awards):
    key = _insert_award(app, FOREIGN_PK, FOREIGN_TITLE)

    logged_in_client.post(f'/professor/awards/student/delete/{key}')

    with app.app_context():
        row = execute_query(
            'SELECT * FROM STUDENTAWARDS WHERE `Award Key` = %s',
            (key,), fetchone=True)
    assert row is not None, "someone else's award must not be deletable"


def test_cannot_duplicate_foreign_award(app, logged_in_client,
                                        seed_professor, clean_awards):
    key = _insert_award(app, FOREIGN_PK, FOREIGN_TITLE)

    logged_in_client.post(f'/professor/awards/student/duplicate/{key}')

    with app.app_context():
        rows = execute_query(
            'SELECT `Award Key` FROM AWARDS WHERE Title = %s',
            (FOREIGN_TITLE,))
    assert len(rows) == 1, 'duplicating a foreign award must be refused'


def test_cannot_edit_foreign_award(app, logged_in_client,
                                   seed_professor, clean_awards):
    key = _insert_award(app, FOREIGN_PK, FOREIGN_TITLE,
                        student='Original Student')

    logged_in_client.post(f'/professor/awards/student/edit/{key}', data={
        'student_name': 'Hijacked Student',
        'award_title': FOREIGN_TITLE,
        'amount': '999.00',
        'category': 'Research',
        'type': 'Graduate',
        'year': '2020',
    })

    with app.app_context():
        row = execute_query(
            'SELECT Student FROM STUDENTAWARDS WHERE `Award Key` = %s',
            (key,), fetchone=True)
    assert row['Student'] == 'Original Student', \
        "someone else's award must not be editable"
