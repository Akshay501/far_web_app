"""
CAS slice 3: the Clarkson employee ID, from the CAS carLicense attribute.

Prof. Brian confirmed that Clarkson's CAS releases each person's employee
ID in the attribute called carLicense (an LDAP name re-used by Clarkson).
The NetID stays the LOGIN key; the employee ID is profile data stored on
PROFESSOR.EmployeeID. The contract:

  format      Clarkson's EMPLID is ALWAYS exactly 7 digits (Josh Fiske,
              2026-10-15). That is the default rule, and it is what keeps
              a licence plate like ABC1234 out. Other institutions use
              other identifiers, so the rule is a setting:
              EMPLOYEE_ID_PATTERN (a regular expression).
  extract     employee_id_from(attributes, name, pattern) -> ID or None
                - one value, or the same value repeated -> that value
                - two DIFFERENT values -> None (ambiguous, never guess)
                - missing / blank / wrong format -> None
                - stored as text: a leading zero is never lost
  config      CAS_EMPLOYEE_ID_ATTRIBUTE, default 'carLicense'
  form        admin "Add Professor" has an optional Employee ID field
  creation    stored on PROFESSOR.EmployeeID; a duplicate is refused
              and nothing is created; blank stores NULL
  CAS login   for a PROFESSOR account:
                empty in FAR      -> filled in from CAS
                same as CAS       -> nothing changes
                different         -> NOT overwritten; warning logged
                taken by another  -> NOT written; warning logged
              admins (no PROFESSOR row) are skipped
              every case still logs the person in: the ID is never
              allowed to block a sign-in
              the ID value itself NEVER appears in the logs
  dashboard   no fake 'EMP001' when the ID is unknown

The extract/config/form groups are hermetic. The rest use the TEST
database (PROFESSOR.EmployeeID already exists there: varchar(50) UNIQUE).
"""
import logging

import pytest

from app.utils import execute_query
from tests.test_cas_login import (CAS, _Resp, _success,  # noqa: F401
                                  _logged_in_as, fake_cas, cas_on,
                                  netid_professor)

EMP = '1234567'          # Clarkson format: exactly 7 digits
OTHER_EMP = '7654321'
OTHER_PROF_KEY = 9002


def _car(value):
    return f'<cas:carLicense>{value}</cas:carLicense>'


# ================================================================= extract

@pytest.mark.parametrize('attrs, expected', [
    ({'carLicense': EMP}, EMP),
    ({'carLicense': f'  {EMP} '}, EMP),
    ({'carLicense': [EMP, EMP]}, EMP),
    ({'carLicense': [EMP, OTHER_EMP]}, None),
    ({'carLicense': ''}, None),
    ({}, None),
    ({'carLicense': 'ABC1234'}, None),        # a NY licence plate
    ({'carLicense': 'NY ABC 123'}, None),
    ({'carLicense': '123456'}, None),         # too short
    ({'carLicense': '12345678'}, None),       # too long
    ({'carLicense': '123-4567'}, None),
])
def test_employee_id_from(attrs, expected):
    from app.cas import employee_id_from, CLARKSON_EMPLOYEE_ID
    assert employee_id_from(attrs, 'carLicense',
                            CLARKSON_EMPLOYEE_ID) == expected


def test_employee_id_from_another_attribute_and_pattern():
    import re
    from app.cas import employee_id_from
    assert employee_id_from({'employeeNumber': 'E-00042'}, 'employeeNumber',
                            re.compile(r'^E-\d{5}$')) == 'E-00042'


def test_validate_ticket_reads_carlicense(fake_cas):
    from app.cas import validate_ticket, employee_id_from
    fake_cas['state']['response'] = _Resp(_success(attrs=_car(EMP)))
    _netid, attrs = validate_ticket(CAS, 'ST-1', 'http://localhost/cas/callback')
    assert employee_id_from(attrs, 'carLicense') == EMP   # default rule


# ================================================================== config

def test_attribute_name_defaults_to_carlicense(monkeypatch):
    from app import create_app
    monkeypatch.delenv('CAS_EMPLOYEE_ID_ATTRIBUTE', raising=False)
    assert create_app().config['CAS_EMPLOYEE_ID_ATTRIBUTE'] == 'carLicense'


def test_attribute_name_from_environment(monkeypatch):
    from app import create_app
    monkeypatch.setenv('CAS_EMPLOYEE_ID_ATTRIBUTE', 'employeeNumber')
    assert create_app().config['CAS_EMPLOYEE_ID_ATTRIBUTE'] == \
        'employeeNumber'


def test_id_pattern_defaults_to_seven_digits(monkeypatch):
    from app import create_app
    monkeypatch.delenv('EMPLOYEE_ID_PATTERN', raising=False)
    pattern = create_app().config['EMPLOYEE_ID_PATTERN']
    assert pattern.match('1234567') and not pattern.match('ABC1234')


def test_id_pattern_from_environment(monkeypatch):
    from app import create_app
    monkeypatch.setenv('EMPLOYEE_ID_PATTERN', r'^E-\d{5}$')
    assert create_app().config['EMPLOYEE_ID_PATTERN'].match('E-00042')


# ==================================================================== form

FORM_BASE = dict(
    first_name='Emp', middle_name='', last_name='Loyee',
    email='pytest.empid@clarkson.edu',
    department='Electrical and Computer Engineering',
    google_id='', orcid='', scopus_id='', netid='',
)


def _form(app, **data):
    from app.forms import AdminCreateProfessorForm
    with app.test_request_context(method='POST', data=dict(FORM_BASE, **data)):
        form = AdminCreateProfessorForm()
        form.department.choices = [(FORM_BASE['department'],) * 2]
        return form.validate(), form.errors


def test_employee_id_optional(app):
    ok, errors = _form(app, employee_id='')
    assert ok, errors


def test_seven_digit_employee_id_accepted(app):
    ok, errors = _form(app, employee_id=EMP)
    assert ok, errors


@pytest.mark.parametrize('bad', ['ABC1234', '123456', '12345678',
                                 '123 4567', '123-4567'])
def test_wrong_format_employee_id_refused(app, bad):
    ok, errors = _form(app, employee_id=bad)
    assert not ok
    assert any('7 digits' in m for m in errors['employee_id'])


def test_form_follows_the_configured_pattern(app):
    import re
    app.config['EMPLOYEE_ID_PATTERN'] = re.compile(r'^E-\d{5}$')
    app.config['EMPLOYEE_ID_HINT'] = 'An Employee ID looks like E-00042.'
    assert _form(app, employee_id='E-00042')[0]
    ok, errors = _form(app, employee_id=EMP)
    assert not ok and 'E-00042' in errors['employee_id'][0]


# ================================================================ creation

NEW_EMAIL = FORM_BASE['email']
OTHER_EMAIL = 'pytest.empid2@clarkson.edu'


@pytest.fixture
def empid_env(scaffold, app):
    yield scaffold
    with app.app_context():
        for email in (NEW_EMAIL, OTHER_EMAIL):
            row = execute_query('SELECT ProfessorKey FROM users WHERE Email=%s',
                                (email,), fetchone=True)
            execute_query('DELETE FROM users WHERE Email=%s',
                          (email,), commit=True)
            if row and row.get('ProfessorKey'):
                execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey=%s',
                              (row['ProfessorKey'],), commit=True)


def _employee_id_for_email(app, email):
    with app.app_context():
        row = execute_query(
            'SELECT p.EmployeeID FROM PROFESSOR p '
            'JOIN users u ON u.ProfessorKey = p.ProfessorKey '
            'WHERE u.Email = %s', (email,), fetchone=True)
        return row['EmployeeID'] if row else 'NO ACCOUNT'


def test_admin_create_stores_employee_id(admin_client, empid_env, app):
    resp = admin_client.post('/admin/professor/new',
                             data=dict(FORM_BASE, employee_id=f' {EMP} '))
    assert resp.status_code == 302
    assert _employee_id_for_email(app, NEW_EMAIL) == EMP


def test_duplicate_employee_id_refused(admin_client, empid_env, app):
    admin_client.post('/admin/professor/new',
                      data=dict(FORM_BASE, employee_id=EMP))
    resp = admin_client.post('/admin/professor/new',
                             data=dict(FORM_BASE, email=OTHER_EMAIL,
                                       employee_id=EMP))
    assert resp.status_code == 200
    assert b'Employee ID' in resp.data
    assert _employee_id_for_email(app, OTHER_EMAIL) == 'NO ACCOUNT'


def test_create_without_employee_id_stores_null(admin_client, empid_env, app):
    resp = admin_client.post('/admin/professor/new',
                             data=dict(FORM_BASE, employee_id=''))
    assert resp.status_code == 302
    assert _employee_id_for_email(app, NEW_EMAIL) is None


# =============================================================== CAS login

def _set_emp(app, professor_key, value):
    with app.app_context():
        execute_query('UPDATE PROFESSOR SET EmployeeID=%s WHERE ProfessorKey=%s',
                      (value, professor_key), commit=True)


def _get_emp(app, professor_key):
    with app.app_context():
        return execute_query(
            'SELECT EmployeeID FROM PROFESSOR WHERE ProfessorKey=%s',
            (professor_key,), fetchone=True)['EmployeeID']


@pytest.fixture
def prof(app, netid_professor):
    """The seeded professor with a NetID and NO employee ID yet."""
    _set_emp(app, netid_professor['professor_key'], None)
    yield netid_professor
    _set_emp(app, netid_professor['professor_key'], None)


@pytest.fixture
def other_prof(app):
    """A second professor who already holds OTHER_EMP."""
    with app.app_context():
        execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey=%s',
                      (OTHER_PROF_KEY,), commit=True)
        execute_query(
            'INSERT INTO PROFESSOR (ProfessorKey, FirstName, LastName, '
            'Department, EmployeeID) VALUES (%s, %s, %s, %s, %s)',
            (OTHER_PROF_KEY, 'Other', 'Professor', 'Physics', OTHER_EMP),
            commit=True)
    yield OTHER_PROF_KEY
    with app.app_context():
        execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey=%s',
                      (OTHER_PROF_KEY,), commit=True)


def _cas_login(client, fake_cas, attrs=''):
    fake_cas['state']['response'] = _Resp(_success(attrs=attrs))
    return client.get('/cas/callback?ticket=ST-1')


def _assert_never_logged(caplog, *values):
    text = caplog.text
    for v in values:
        assert v not in text, 'an employee ID was written to the log'


def test_empty_id_is_filled_from_cas(client, cas_on, fake_cas, prof, app,
                                     caplog):
    caplog.set_level(logging.DEBUG)
    resp = _cas_login(client, fake_cas, _car(EMP))
    assert resp.status_code == 302
    assert _logged_in_as(client) == str(prof['user_id'])
    assert _get_emp(app, prof['professor_key']) == EMP
    _assert_never_logged(caplog, EMP)


def test_matching_id_left_alone(client, cas_on, fake_cas, prof, app):
    _set_emp(app, prof['professor_key'], EMP)
    resp = _cas_login(client, fake_cas, _car(EMP))
    assert resp.status_code == 302
    assert _get_emp(app, prof['professor_key']) == EMP


def test_different_id_not_overwritten_but_still_logged_in(
        client, cas_on, fake_cas, prof, app, caplog):
    caplog.set_level(logging.DEBUG)
    _set_emp(app, prof['professor_key'], OTHER_EMP)
    resp = _cas_login(client, fake_cas, _car(EMP))
    assert resp.status_code == 302
    assert _logged_in_as(client) == str(prof['user_id'])
    assert _get_emp(app, prof['professor_key']) == OTHER_EMP
    assert 'does not match' in caplog.text
    _assert_never_logged(caplog, EMP, OTHER_EMP)


def test_id_held_by_another_professor_not_written(
        client, cas_on, fake_cas, prof, other_prof, app, caplog):
    caplog.set_level(logging.DEBUG)
    resp = _cas_login(client, fake_cas, _car(OTHER_EMP))
    assert resp.status_code == 302
    assert _logged_in_as(client) == str(prof['user_id'])
    assert _get_emp(app, prof['professor_key']) is None
    assert _get_emp(app, other_prof) == OTHER_EMP
    assert 'another professor' in caplog.text
    _assert_never_logged(caplog, OTHER_EMP)


def test_no_carlicense_logs_in_and_changes_nothing(
        client, cas_on, fake_cas, prof, app):
    resp = _cas_login(client, fake_cas, '')
    assert resp.status_code == 302
    assert _logged_in_as(client) == str(prof['user_id'])
    assert _get_emp(app, prof['professor_key']) is None


def test_wrong_format_from_cas_is_ignored(client, cas_on, fake_cas, prof,
                                          app):
    resp = _cas_login(client, fake_cas, _car('ABC1234'))
    assert resp.status_code == 302
    assert _logged_in_as(client) == str(prof['user_id'])
    assert _get_emp(app, prof['professor_key']) is None


def test_configured_attribute_name_is_used(client, cas_on, fake_cas, prof,
                                           app):
    app.config['CAS_EMPLOYEE_ID_ATTRIBUTE'] = 'employeeNumber'
    _cas_login(client, fake_cas,
               f'<cas:employeeNumber>{EMP}</cas:employeeNumber>'
               + _car(OTHER_EMP))
    assert _get_emp(app, prof['professor_key']) == EMP


def test_sync_failure_never_blocks_login(client, cas_on, fake_cas, prof,
                                         monkeypatch):
    import app.routes.auth as auth_mod

    def broken(*a, **k):
        raise RuntimeError('database hiccup')
    monkeypatch.setattr(auth_mod, 'sync_employee_id', broken)
    resp = _cas_login(client, fake_cas, _car(EMP))
    assert resp.status_code == 302
    assert _logged_in_as(client) == str(prof['user_id'])


ADMIN_ID = 9004
ADMIN_NETID = 'pytestadminnetid'


@pytest.fixture
def netid_admin(app):
    with app.app_context():
        execute_query('DELETE FROM users WHERE UserID=%s', (ADMIN_ID,),
                      commit=True)
        execute_query(
            'INSERT INTO users (UserID, Name, Email, Password, Role, '
            'ProfessorKey, NetID) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (ADMIN_ID, 'CAS Admin', 'pytest.casadmin@clarkson.edu', 'x',
             'admin', None, ADMIN_NETID), commit=True)
    yield ADMIN_ID
    with app.app_context():
        execute_query('DELETE FROM users WHERE UserID=%s', (ADMIN_ID,),
                      commit=True)


def test_admin_login_skips_the_sync(client, cas_on, fake_cas, netid_admin,
                                    monkeypatch):
    import app.routes.auth as auth_mod
    calls = []
    monkeypatch.setattr(auth_mod, 'sync_employee_id',
                        lambda *a, **k: calls.append(a))
    fake_cas['state']['response'] = _Resp(_success(user=ADMIN_NETID,
                                                   attrs=_car(EMP)))
    resp = client.get('/cas/callback?ticket=ST-1')
    assert resp.status_code == 302
    assert _logged_in_as(client) == str(ADMIN_ID)
    assert calls == []


# =============================================================== dashboard

def test_dashboard_shows_no_fake_employee_id(logged_in_client, app,
                                             seed_professor):
    _set_emp(app, seed_professor['professor_key'], None)
    resp = logged_in_client.get('/professor/dashboard')
    assert resp.status_code == 200
    assert b'EMP001' not in resp.data
