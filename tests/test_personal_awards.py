"""
Tests for the personal-awards repair (GitHub Issue #13 — same disease
as student awards, second table).

PERSONALAWARDS is a three-column junction table: (`Award Key`,
ProfessorKey) composite PK + Amount. Title/`Award Type`/Year live in
the AWARDS parent. The composite PK means one AWARDS row may be linked
by SEVERAL professors — so a parent may only be cleaned up when nobody
else references it.

Written BEFORE the fix. Against current code:
  - add errors (INSERT references Title/AwardType/Year on the junction
    table — error 1054; adding has never worked)
  - modal edit errors the same way, and its GET prefill reads phantom
    columns, so the dialog opens blank
  - inline edit has NO ownership gate (any professor can edit any
    award id — and shared parents make that edit propagate)
  - duplicate drops Amount and NameErrors on a missing/foreign id
  - delete orphans the AWARDS parent

One test passes today on purpose: the shared-parent guard, which must
STAY green through the fix.
"""
import pytest

from app.utils import execute_query

FOREIGN_PK = 9002

OWN_TITLE = 'Own Personal Award PLUGH2'
FOREIGN_TITLE = 'Foreign Personal Award XYZZY2'
FORM_TITLE = 'Added Personal Via Form QWERTY2'
EDITED_TITLE = 'Edited Personal Title QQ7'


def _insert_pair(app, professor_key, title, amount=None,
                 award_type='University', year=2025):
    """Seed an AWARDS parent + PERSONALAWARDS link, returning Award Key."""
    with app.app_context():
        key = execute_query(
            'INSERT INTO AWARDS (Title, Year, `Award Type`) '
            'VALUES (%s, %s, %s)',
            (title, year, award_type), commit=True, lastrowid=True)
        execute_query(
            'INSERT INTO PERSONALAWARDS (`Award Key`, ProfessorKey, Amount) '
            'VALUES (%s, %s, %s)',
            (key, professor_key, amount), commit=True)
        return key


@pytest.fixture
def clean_pawards(app):
    """Remove every row these tests may create, children first."""
    yield
    with app.app_context():
        for title in (OWN_TITLE, FOREIGN_TITLE, FORM_TITLE, EDITED_TITLE,
                      'Hijacked Personal Title'):
            rows = execute_query(
                'SELECT `Award Key` FROM AWARDS WHERE Title = %s', (title,))
            for r in rows:
                execute_query(
                    'DELETE FROM PERSONALAWARDS WHERE `Award Key` = %s',
                    (r['Award Key'],), commit=True)
                execute_query(
                    'DELETE FROM AWARDS WHERE `Award Key` = %s',
                    (r['Award Key'],), commit=True)


@pytest.fixture
def foreign_professor(app):
    """PERSONALAWARDS.ProfessorKey is a REAL foreign key to PROFESSOR
    (unlike STUDENTAWARDS' plain column — discovered by this suite's
    first red run), so the foreign owner must actually exist. Its
    ON DELETE CASCADE cleans any leftover links on teardown."""
    with app.app_context():
        execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey = %s',
                      (FOREIGN_PK,), commit=True)
        execute_query(
            'INSERT INTO PROFESSOR '
            '(ProfessorKey, FirstName, LastName, Department) '
            'VALUES (%s, %s, %s, %s)',
            (FOREIGN_PK, 'Foreign', 'Pytest', 'Computer Science'),
            commit=True)
    yield FOREIGN_PK
    with app.app_context():
        execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey = %s',
                      (FOREIGN_PK,), commit=True)


def _award_row(app, title):
    with app.app_context():
        return execute_query(
            'SELECT * FROM AWARDS WHERE Title = %s', (title,), fetchone=True)


def _link_row(app, key, professor_key):
    with app.app_context():
        return execute_query(
            'SELECT * FROM PERSONALAWARDS '
            'WHERE `Award Key` = %s AND ProfessorKey = %s',
            (key, professor_key), fetchone=True)


# ------------------------------------------------------------------- add

def test_add_personal_award_creates_owned_rows(app, logged_in_client,
                                               seed_professor,
                                               clean_pawards):
    resp = logged_in_client.post('/professor/awards', data={
        'form_type': 'personal',
        'title': FORM_TITLE,
        'type': 'University',
        'year': '2025',
    })
    assert resp.status_code in (200, 302)

    parent = _award_row(app, FORM_TITLE)
    assert parent is not None, 'AWARDS parent row should exist'
    assert parent['Year'] == 2025
    assert parent['Award Type'] == 'University'

    link = _link_row(app, parent['Award Key'],
                     seed_professor['professor_key'])
    assert link is not None, 'owned PERSONALAWARDS link should exist'

    # And it must actually appear on the page.
    page = logged_in_client.get('/professor/awards')
    assert FORM_TITLE.encode() in page.data


# ------------------------------------------------------------------ edit

def test_modal_edit_updates_the_award(app, logged_in_client,
                                      seed_professor, clean_pawards):
    key = _insert_pair(app, seed_professor['professor_key'], OWN_TITLE)

    logged_in_client.post(f'/professor/awards/personal/edit/{key}', data={
        'title': EDITED_TITLE,
        'type': 'School',
        'year': '2020',
    })

    row = _award_row(app, EDITED_TITLE)
    assert row is not None, 'the edit must reach the AWARDS parent'
    assert row['Year'] == 2020
    assert row['Award Type'] == 'School'


def test_modal_edit_prefills_current_values(app, logged_in_client,
                                            seed_professor, clean_pawards):
    key = _insert_pair(app, seed_professor['professor_key'], OWN_TITLE)

    resp = logged_in_client.get(f'/professor/awards/personal/edit/{key}')

    assert resp.status_code == 200
    assert OWN_TITLE.encode() in resp.data, \
        'the edit dialog must prefill the current title, not open blank'


def test_cannot_edit_foreign_award_inline(app, logged_in_client,
                                          seed_professor, clean_pawards,
                                          foreign_professor):
    key = _insert_pair(app, FOREIGN_PK, FOREIGN_TITLE)

    logged_in_client.post(f'/professor/awards/personal/edit/{key}', data={
        'inline_edit': '1',
        'title': 'Hijacked Personal Title',
        'type': 'School',
        'year': '2020',
    })

    row = _award_row(app, FOREIGN_TITLE)
    assert row is not None, \
        "someone else's award must survive an inline edit attempt"


def test_cannot_edit_foreign_award_modal(app, logged_in_client,
                                         seed_professor, clean_pawards,
                                         foreign_professor):
    key = _insert_pair(app, FOREIGN_PK, FOREIGN_TITLE)

    logged_in_client.post(f'/professor/awards/personal/edit/{key}', data={
        'title': 'Hijacked Personal Title',
        'type': 'School',
        'year': '2020',
    })

    row = _award_row(app, FOREIGN_TITLE)
    assert row is not None, \
        "someone else's award must survive a modal edit attempt"


# ------------------------------------------------------------- duplicate

def test_duplicate_copies_amount(app, logged_in_client, seed_professor,
                                 clean_pawards):
    key = _insert_pair(app, seed_professor['professor_key'], OWN_TITLE,
                       amount=250)

    logged_in_client.post(f'/professor/awards/personal/duplicate/{key}')

    with app.app_context():
        rows = execute_query(
            'SELECT pa.Amount FROM PERSONALAWARDS pa '
            'JOIN AWARDS a ON pa.`Award Key` = a.`Award Key` '
            'WHERE a.Title = %s AND pa.`Award Key` <> %s',
            (OWN_TITLE, key))
    assert len(rows) == 1, 'the duplicate link should exist'
    assert float(rows[0]['Amount'] or 0) == 250.0, \
        'duplicating must copy the Amount'


def test_duplicate_foreign_is_refused_without_crash(app, logged_in_client,
                                                    seed_professor,
                                                    clean_pawards,
                                                    foreign_professor):
    key = _insert_pair(app, FOREIGN_PK, FOREIGN_TITLE)

    resp = logged_in_client.post(
        f'/professor/awards/personal/duplicate/{key}')

    assert resp.status_code in (200, 302), \
        'a foreign id must be refused cleanly, not crash'
    with app.app_context():
        rows = execute_query(
            'SELECT `Award Key` FROM AWARDS WHERE Title = %s',
            (FOREIGN_TITLE,))
    assert len(rows) == 1, 'no copy of a foreign award may be created'


# ---------------------------------------------------------------- delete

def test_delete_removes_unshared_parent(app, logged_in_client,
                                        seed_professor, clean_pawards):
    key = _insert_pair(app, seed_professor['professor_key'], OWN_TITLE)

    logged_in_client.post(f'/professor/awards/personal/delete/{key}')

    assert _link_row(app, key, seed_professor['professor_key']) is None
    assert _award_row(app, OWN_TITLE) is None, \
        'an AWARDS parent nobody references anymore must be removed'


def test_delete_keeps_parent_shared_with_another_professor(
        app, logged_in_client, seed_professor, clean_pawards,
        foreign_professor):
    """GREEN today, and must STAY green: the composite PK means another
    professor may link the same AWARDS row — deleting my link must not
    take their award with it."""
    key = _insert_pair(app, seed_professor['professor_key'], OWN_TITLE)
    with app.app_context():
        execute_query(
            'INSERT INTO PERSONALAWARDS (`Award Key`, ProfessorKey, Amount) '
            'VALUES (%s, %s, %s)', (key, FOREIGN_PK, None), commit=True)

    logged_in_client.post(f'/professor/awards/personal/delete/{key}')

    assert _link_row(app, key, seed_professor['professor_key']) is None
    assert _link_row(app, key, FOREIGN_PK) is not None, \
        "the other professor's link must survive"
    assert _award_row(app, OWN_TITLE) is not None, \
        'a parent still referenced by someone must survive'
