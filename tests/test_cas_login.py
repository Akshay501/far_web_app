"""
CAS slice 2: logging in through Clarkson's CAS.

The flow:
  1. GET /login            -> redirect to {CAS}/login?service=<our callback>
  2. the user signs in at Clarkson (the app never sees a password)
  3. CAS redirects to      /cas/callback?ticket=ST-...
  4. the app validates the ticket SERVER-TO-SERVER at
                           {CAS}/p3/serviceValidate  (hard timeout)
  5. CAS answers with the NetID; the app looks it up in users.NetID
       found     -> logged in as that account
       not found -> turned away (Brian, 2026-10-10: admin-created only)

Rules the tests pin down:
  - the NetID comes ONLY from CAS's answer, never from the query string
  - a failed / timed-out / malformed validation logs nobody in
  - the service URL sent to CAS for validation is the one sent at login
  - a session is cleared before logging in (no session fixation)
  - emergency password login at /admin-login works for ADMINS only
  - while CAS is on, password login at /login and self-registration
    are closed; professors have no password to change
  - logout also ends the CAS session
  - with CAS off, everything behaves exactly as before

CAS itself is faked by monkeypatching requests.get inside app.cas.
Tests marked as needing the database use the TEST database.
"""
import pytest
import requests
from urllib.parse import urlparse, parse_qs

from app.utils import execute_query

CAS = 'https://cas.example.edu/cas'
NETID = 'pytestnetid'
CALLBACK = 'http://localhost/cas/callback'


def _success(user=NETID, attrs=''):
    return f"""<cas:serviceResponse xmlns:cas='http://www.yale.edu/tp/cas'>
  <cas:authenticationSuccess>
    <cas:user>{user}</cas:user>
    <cas:attributes>{attrs}</cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>"""


FAILURE = """<cas:serviceResponse xmlns:cas='http://www.yale.edu/tp/cas'>
  <cas:authenticationFailure code="INVALID_TICKET">
    Ticket ST-1 not recognized
  </cas:authenticationFailure>
</cas:serviceResponse>"""


class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status


@pytest.fixture
def fake_cas(monkeypatch):
    """Replace the network call to CAS. Records every call it receives."""
    import app.cas as cas_mod
    calls = []
    state = {'response': _Resp(_success()), 'raise': None}

    def fake_get(url, params=None, timeout=None, **kw):
        calls.append({'url': url, 'params': params or {}, 'timeout': timeout})
        if state['raise']:
            raise state['raise']
        return state['response']

    monkeypatch.setattr(cas_mod.requests, 'get', fake_get)
    return {'calls': calls, 'state': state}


@pytest.fixture
def cas_on(app):
    app.config['CAS_SERVER_URL'] = CAS
    return app


@pytest.fixture
def no_db(monkeypatch):
    """For paths that must be refused BEFORE any database access."""
    def boom(*a, **k):
        raise AssertionError('database was queried on a path that '
                             'must refuse before touching it')
    import app.routes.auth as auth_mod
    monkeypatch.setattr(auth_mod, 'execute_query', boom)


@pytest.fixture
def netid_professor(app, seed_professor):
    """The seeded professor, given a NetID."""
    with app.app_context():
        execute_query('UPDATE users SET NetID=%s WHERE UserID=%s',
                      (NETID, seed_professor['user_id']), commit=True)
    yield seed_professor
    with app.app_context():
        execute_query('UPDATE users SET NetID=NULL WHERE UserID=%s',
                      (seed_professor['user_id'],), commit=True)


def _logged_in_as(client):
    with client.session_transaction() as s:
        return s.get('_user_id')


# =================================================== the CAS module itself

def test_login_url_carries_the_service(app):
    from app.cas import login_url
    url = login_url(CAS, CALLBACK)
    parsed = urlparse(url)
    assert url.startswith(CAS + '/login?')
    assert parse_qs(parsed.query)['service'] == [CALLBACK]


def test_validate_returns_the_netid(fake_cas):
    from app.cas import validate_ticket
    netid, attrs = validate_ticket(CAS, 'ST-1', CALLBACK)
    assert netid == NETID


def test_validate_reads_attributes(fake_cas):
    from app.cas import validate_ticket
    fake_cas['state']['response'] = _Resp(_success(
        attrs='<cas:mail>a@clarkson.edu</cas:mail>'
              '<cas:gecos>faculty</cas:gecos>'))
    netid, attrs = validate_ticket(CAS, 'ST-1', CALLBACK)
    assert attrs == {'mail': 'a@clarkson.edu', 'gecos': 'faculty'}


def test_validate_lowercases_and_strips_the_netid(fake_cas):
    from app.cas import validate_ticket
    fake_cas['state']['response'] = _Resp(_success(user='  PyTestNetID '))
    assert validate_ticket(CAS, 'ST-1', CALLBACK)[0] == NETID


def test_validate_asks_cas_3_with_ticket_service_and_timeout(fake_cas):
    from app.cas import validate_ticket, CAS_TIMEOUT
    validate_ticket(CAS, 'ST-1', CALLBACK)
    call = fake_cas['calls'][0]
    assert call['url'] == CAS + '/p3/serviceValidate'
    assert call['params'] == {'ticket': 'ST-1', 'service': CALLBACK}
    assert call['timeout'] == CAS_TIMEOUT and CAS_TIMEOUT <= 15


def test_rejected_ticket_raises(fake_cas):
    from app.cas import validate_ticket, CASError
    fake_cas['state']['response'] = _Resp(FAILURE)
    with pytest.raises(CASError) as exc:
        validate_ticket(CAS, 'ST-1', CALLBACK)
    assert 'INVALID_TICKET' in str(exc.value)


@pytest.mark.parametrize('problem', [
    requests.Timeout('slow'),
    requests.ConnectionError('down'),
])
def test_unreachable_cas_raises(fake_cas, problem):
    from app.cas import validate_ticket, CASError
    fake_cas['state']['raise'] = problem
    with pytest.raises(CASError):
        validate_ticket(CAS, 'ST-1', CALLBACK)


@pytest.mark.parametrize('resp', [
    _Resp('<html>Server Error</html>', status=500),
    _Resp('not xml at all'),
    _Resp("<cas:serviceResponse xmlns:cas='http://www.yale.edu/tp/cas'/>"),
    _Resp(_success(user='')),
])
def test_unusable_answers_raise(fake_cas, resp):
    from app.cas import validate_ticket, CASError
    fake_cas['state']['response'] = resp
    with pytest.raises(CASError):
        validate_ticket(CAS, 'ST-1', CALLBACK)


# ===================================================== CAS off: unchanged

def test_cas_off_login_shows_the_password_form(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'type="password"' in resp.data


def test_cas_off_callback_does_not_exist(client):
    assert client.get('/cas/callback?ticket=ST-1').status_code == 404


# ================================================= CAS on: the login flow

def test_cas_on_login_redirects_to_cas(cas_on, client):
    resp = client.get('/login')
    assert resp.status_code == 302
    loc = resp.headers['Location']
    assert loc.startswith(CAS + '/login?')
    assert parse_qs(urlparse(loc).query)['service'] == [CALLBACK]


def test_cas_on_password_post_to_login_is_refused(cas_on, client, no_db):
    """No back door: a professor cannot skip CAS by posting a password."""
    resp = client.post('/login', data={'email': 'x@clarkson.edu',
                                       'password': 'whatever'})
    assert resp.status_code in (302, 405)
    assert _logged_in_as(client) is None


def test_callback_without_ticket_is_refused(cas_on, client, no_db):
    resp = client.get('/cas/callback')
    assert resp.status_code == 400
    assert _logged_in_as(client) is None


def test_bad_ticket_logs_nobody_in(cas_on, client, fake_cas, no_db):
    fake_cas['state']['response'] = _Resp(FAILURE)
    resp = client.get('/cas/callback?ticket=ST-1')
    assert resp.status_code == 403
    assert _logged_in_as(client) is None


def test_netid_in_query_string_is_ignored(cas_on, client, fake_cas, no_db):
    """Only CAS's answer may name the user — never the URL."""
    fake_cas['state']['response'] = _Resp(FAILURE)
    resp = client.get(f'/cas/callback?ticket=ST-1&netid={NETID}'
                      f'&user={NETID}')
    assert resp.status_code == 403
    assert _logged_in_as(client) is None


def test_cas_down_shows_a_clear_message(cas_on, client, fake_cas, no_db):
    fake_cas['state']['raise'] = requests.Timeout('slow')
    resp = client.get('/cas/callback?ticket=ST-1')
    assert resp.status_code == 503
    assert b'Clarkson' in resp.data
    assert _logged_in_as(client) is None


def test_validation_uses_the_same_service_url(cas_on, client, fake_cas, no_db):
    fake_cas['state']['response'] = _Resp(FAILURE)
    login_loc = client.get('/login').headers['Location']
    sent = parse_qs(urlparse(login_loc).query)['service'][0]
    client.get('/cas/callback?ticket=ST-1')
    assert fake_cas['calls'][0]['params']['service'] == sent


# ---------------------------------------------------- needs the database

def test_known_netid_is_logged_in(cas_on, client, fake_cas, netid_professor):
    resp = client.get('/cas/callback?ticket=ST-1')
    assert resp.status_code == 302
    assert '/professor/dashboard' in resp.headers['Location']
    assert _logged_in_as(client) == str(netid_professor['user_id'])


def test_unknown_netid_is_turned_away(cas_on, client, fake_cas, seed_professor):
    """Brian, 2026-10-10: admin-created professors only."""
    fake_cas['state']['response'] = _Resp(_success(user='nosuchnetid'))
    resp = client.get('/cas/callback?ticket=ST-1')
    assert resp.status_code == 403
    assert b'nosuchnetid' in resp.data
    assert _logged_in_as(client) is None


def test_unknown_netid_creates_nothing(cas_on, client, fake_cas, app):
    fake_cas['state']['response'] = _Resp(_success(user='nosuchnetid'))
    client.get('/cas/callback?ticket=ST-1')
    with app.app_context():
        assert execute_query('SELECT UserID FROM users WHERE NetID=%s',
                             ('nosuchnetid',), fetchone=True) is None


def test_session_is_cleared_before_login(cas_on, client, fake_cas,
                                         netid_professor):
    with client.session_transaction() as s:
        s['planted'] = 'attacker-value'
    client.get('/cas/callback?ticket=ST-1')
    with client.session_transaction() as s:
        assert 'planted' not in s


# ================================================ emergency admin password

def test_admin_login_page_offered_under_cas(cas_on, client):
    resp = client.get('/admin-login')
    assert resp.status_code == 200
    assert b'type="password"' in resp.data


def test_admin_can_use_the_emergency_password(cas_on, app, client):
    from tests.conftest import ADMIN_ID, ADMIN_EMAIL, ADMIN_PASSWORD
    from werkzeug.security import generate_password_hash
    with app.app_context():
        execute_query('DELETE FROM users WHERE UserID=%s', (ADMIN_ID,),
                      commit=True)
        execute_query(
            'INSERT INTO users (UserID, Name, Email, Password, Role, '
            'ProfessorKey) VALUES (%s,%s,%s,%s,%s,%s)',
            (ADMIN_ID, 'Pytest Admin', ADMIN_EMAIL,
             generate_password_hash(ADMIN_PASSWORD), 'admin', None),
            commit=True)
    try:
        resp = client.post('/admin-login', data={'email': ADMIN_EMAIL,
                                                 'password': ADMIN_PASSWORD})
        assert resp.status_code == 302
        assert '/admin' in resp.headers['Location']
        assert _logged_in_as(client) == str(ADMIN_ID)
    finally:
        with app.app_context():
            execute_query('DELETE FROM users WHERE UserID=%s', (ADMIN_ID,),
                          commit=True)


def test_professor_cannot_use_the_emergency_password(cas_on, client,
                                                     seed_professor):
    resp = client.post('/admin-login', data={
        'email': seed_professor['email'],
        'password': seed_professor['password']})
    assert resp.status_code == 200
    assert _logged_in_as(client) is None


# ====================================== what closes while CAS is switched on

def test_registration_closed_under_cas(cas_on, client, no_db):
    resp = client.get('/register')
    assert resp.status_code == 302
    assert client.post('/register', data={}).status_code == 302


def test_professor_change_password_closed_under_cas(app, logged_in_client):
    app.config['CAS_SERVER_URL'] = CAS
    resp = logged_in_client.get('/change-password')
    assert resp.status_code == 302


def test_logout_also_ends_the_cas_session(cas_on, client):
    resp = client.get('/logout')
    assert resp.status_code == 302
    assert resp.headers['Location'].startswith(CAS + '/logout')


def test_cas_off_logout_unchanged(client):
    resp = client.get('/logout')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
