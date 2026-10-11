"""
CAS slice 1: every account can carry a Clarkson NetID.

CAS tells the app only WHO someone is — their NetID (e.g. "thuguda").
This slice stores that NetID on the users row so slice 2 can look a
CAS login up directly. The contract:

  config      CAS_SERVER_URL comes from the environment (unset = CAS off)
  form        admin "Add Professor" has a NetID field:
                - optional while CAS is off (password login still works)
                - REQUIRED once CAS is on (no NetID = can never log in)
                - a full email is refused with a hint to drop the @part
                - only letters, digits, dot, dash, underscore
  creation    stored lowercased and stripped on users.NetID
              a duplicate NetID is refused; nothing is created
  model       User exposes .netid (None for rows without one)

The first three groups are hermetic. The creation tests hit the TEST
database and need the NetID column (see the commit message for the SQL).
"""
import pytest

from app.utils import execute_query
from app.models import User

NEW_EMAIL = 'pytest.netid@clarkson.edu'
OTHER_EMAIL = 'pytest.netid2@clarkson.edu'

BASE = dict(
    first_name='Net',
    middle_name='',
    last_name='Identity',
    email=NEW_EMAIL,
    department='Electrical and Computer Engineering',
    google_id='',
    orcid='',
    scopus_id='',
)


def _form(app, **data):
    """Build and validate the admin form outside any route."""
    from app.forms import AdminCreateProfessorForm
    payload = dict(BASE, **data)
    with app.test_request_context(method='POST', data=payload):
        form = AdminCreateProfessorForm()
        form.department.choices = [(BASE['department'], BASE['department'])]
        ok = form.validate()
        return ok, form.errors


# ------------------------------------------------------------------ config

def test_cas_server_url_read_from_environment(monkeypatch):
    from app import create_app
    monkeypatch.setenv('CAS_SERVER_URL', 'https://cas.example.edu/cas')
    assert create_app().config['CAS_SERVER_URL'] == \
        'https://cas.example.edu/cas'


def test_cas_is_off_when_unset(monkeypatch):
    from app import create_app
    monkeypatch.delenv('CAS_SERVER_URL', raising=False)
    assert not create_app().config.get('CAS_SERVER_URL')


# -------------------------------------------------------------------- form

def test_netid_optional_while_cas_off(app):
    app.config['CAS_SERVER_URL'] = None
    ok, errors = _form(app, netid='')
    assert ok, errors


def test_netid_required_once_cas_on(app):
    app.config['CAS_SERVER_URL'] = 'https://cas.example.edu/cas'
    ok, errors = _form(app, netid='')
    assert not ok
    assert 'netid' in errors


def test_valid_netid_accepted(app):
    app.config['CAS_SERVER_URL'] = 'https://cas.example.edu/cas'
    ok, errors = _form(app, netid='thuguda')
    assert ok, errors


def test_email_instead_of_netid_gets_a_hint(app):
    ok, errors = _form(app, netid='thuguda@clarkson.edu')
    assert not ok
    assert any('@' in m for m in errors['netid'])


@pytest.mark.parametrize('bad', ['thu guda', 'thu/guda', "o'neil", 'x' * 65])
def test_malformed_netid_refused(app, bad):
    ok, errors = _form(app, netid=bad)
    assert not ok
    assert 'netid' in errors


# ------------------------------------------------------------------- model

def test_user_model_exposes_netid():
    u = User({'UserID': 1, 'Role': 'professor', 'Email': 'a@b.edu',
              'ProfessorKey': 5, 'NetID': 'thuguda'})
    assert u.netid == 'thuguda'


def test_user_model_without_netid_is_none():
    u = User({'UserID': 1, 'Role': 'admin', 'Email': 'a@b.edu'})
    assert u.netid is None


# ---------------------------------------------------------------- creation

@pytest.fixture
def netid_env(scaffold, app):
    yield scaffold
    with app.app_context():
        for email in (NEW_EMAIL, OTHER_EMAIL):
            row = execute_query('SELECT ProfessorKey FROM users WHERE Email=%s',
                                (email,), fetchone=True)
            execute_query('DELETE FROM users WHERE Email=%s',
                          (email,), commit=True)
            if row and row.get('ProfessorKey'):
                execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey=%s',
                              (row['ProfessorKey'], ), commit=True)


def _user(app, email):
    with app.app_context():
        return execute_query('SELECT * FROM users WHERE Email=%s',
                             (email,), fetchone=True)


def test_admin_create_stores_netid_lowercased(admin_client, netid_env, app):
    resp = admin_client.post('/admin/professor/new',
                             data=dict(BASE, netid='  ThuGuda  '))
    assert resp.status_code == 302
    assert _user(app, NEW_EMAIL)['NetID'] == 'thuguda'


def test_duplicate_netid_refused(admin_client, netid_env, app):
    admin_client.post('/admin/professor/new',
                      data=dict(BASE, netid='pytestnetid'))
    resp = admin_client.post('/admin/professor/new',
                             data=dict(BASE, email=OTHER_EMAIL,
                                       netid='PyTestNetID'))
    assert resp.status_code == 200
    assert b'NetID' in resp.data
    assert _user(app, OTHER_EMAIL) is None


def test_create_without_netid_stores_null(admin_client, netid_env, app):
    app.config['CAS_SERVER_URL'] = None
    resp = admin_client.post('/admin/professor/new',
                             data=dict(BASE, netid=''))
    assert resp.status_code == 302
    assert _user(app, NEW_EMAIL)['NetID'] is None
