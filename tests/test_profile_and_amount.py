"""
Phase 0.2's last two form items.

Profile: the registration form has had a department DROPDOWN (fed from
the config list) and a Scopus ID field since day one — the profile page
never caught up. Free-text departments fragment the data ("MAE" vs
"Mechanical & Aerospace"), and without a saved ScopusID the coming
Scopus sync has nothing to key on. refresh_personal_files already
writes scopusid into personal_data.txt, so saving the column completes
the chain.

Awards: PERSONALAWARDS has always had an Amount column, but the insert
hardcoded None — the column was unreachable from the UI
(DEBUGGING_LOG 2026-07-25).
"""
import pytest

from app.utils import execute_query

TITLE_WITH = 'Amount Award ZXQV1'
TITLE_WITHOUT = 'Amount Award ZXQV2'


@pytest.fixture
def clean_amount_awards(app):
    yield
    with app.app_context():
        for title in (TITLE_WITH, TITLE_WITHOUT):
            for r in execute_query(
                    'SELECT `Award Key` FROM AWARDS WHERE Title = %s',
                    (title,)):
                execute_query('DELETE FROM PERSONALAWARDS WHERE `Award Key` = %s',
                              (r['Award Key'],), commit=True)
                execute_query('DELETE FROM AWARDS WHERE `Award Key` = %s',
                              (r['Award Key'],), commit=True)


def test_profile_offers_department_dropdown(logged_in_client, app):
    resp = logged_in_client.get('/professor/profile')
    html = resp.data.decode()
    assert '<select' in html and 'name="department"' in html, \
        'department must be a dropdown, not free text'
    depts = app.config.get('DEPARTMENTS', [])
    assert depts and depts[0] in html, \
        'the dropdown must offer the config department list'


def test_profile_saves_scopus_and_department(logged_in_client, app,
                                             seed_professor):
    depts = app.config.get('DEPARTMENTS', [])
    resp = logged_in_client.post('/professor/profile', data={
        'first_name': 'Test', 'last_name': 'Professor',
        'orcid': '', 'google_id': '',
        'scopus_id': '57210987654',
        'department': depts[0],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        row = execute_query(
            'SELECT ScopusID, Department FROM PROFESSOR '
            'WHERE ProfessorKey = %s',
            (seed_professor['professor_key'],), fetchone=True)
    assert row['ScopusID'] == '57210987654'
    assert row['Department'] == depts[0]


def test_department_outside_list_is_rejected(logged_in_client, app,
                                             seed_professor):
    """SelectField validates against choices: a hand-crafted POST with
    a department not in the config list must not save."""
    resp = logged_in_client.post('/professor/profile', data={
        'first_name': 'Test', 'last_name': 'Professor',
        'orcid': '', 'google_id': '', 'scopus_id': '',
        'department': 'Department Of Made Up Studies',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        row = execute_query(
            'SELECT Department FROM PROFESSOR WHERE ProfessorKey = %s',
            (seed_professor['professor_key'],), fetchone=True)
    assert row['Department'] != 'Department Of Made Up Studies'


def test_personal_award_amount_is_stored(logged_in_client, app,
                                         clean_amount_awards):
    resp = logged_in_client.post('/professor/awards', data={
        'form_type': 'personal', 'title': TITLE_WITH,
        'type': 'University', 'year': '2026', 'amount': '1500.00',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        row = execute_query(
            'SELECT pa.Amount FROM PERSONALAWARDS pa '
            'JOIN AWARDS a ON a.`Award Key` = pa.`Award Key` '
            'WHERE a.Title = %s', (TITLE_WITH,), fetchone=True)
    assert row is not None, 'the award must be inserted'
    assert float(row['Amount']) == 1500.00


def test_personal_award_amount_is_optional(logged_in_client, app,
                                           clean_amount_awards):
    resp = logged_in_client.post('/professor/awards', data={
        'form_type': 'personal', 'title': TITLE_WITHOUT,
        'type': 'University', 'year': '2026', 'amount': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        row = execute_query(
            'SELECT pa.Amount FROM PERSONALAWARDS pa '
            'JOIN AWARDS a ON a.`Award Key` = pa.`Award Key` '
            'WHERE a.Title = %s', (TITLE_WITHOUT,), fetchone=True)
    assert row is not None, 'an award without an amount must still insert'
    assert row['Amount'] is None
