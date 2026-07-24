"""
Tests for professor self-registration (Step 4, slice A: /register).

Written BEFORE the route exists — the first run should fail with 404s.
The contract these tests define:

  GET  /register           -> form renders, department dropdown comes from
                              app config (DEPARTMENTS)
  POST valid               -> users row (role 'professor') + PROFESSOR row
                              (incl. MiddleName and the three IDs) are
                              committed, the professor folder is created
                              via ensure_professor_folder, redirect to login
  non-@clarkson.edu email  -> rejected, nothing created
  duplicate email          -> rejected, existing account untouched
  department not in list   -> rejected
  password mismatch        -> rejected
  folder creation FAILS    -> the account is STILL created (decoupled),
                              a non-blocking warning mentions the folder,
                              and no partial folder exists

These are integration tests: they write to the TEST database and clean up
their rows afterwards.
"""
import pytest

from app.utils import execute_query

REG_EMAIL = 'pytest.registrant@clarkson.edu'
OUTSIDE_EMAIL = 'pytest.outsider@gmail.com'

VALID = dict(
    first_name='Reg',
    middle_name='T',
    last_name='Istrant',
    email=REG_EMAIL,
    password='Sup3rSecret!',
    confirm_password='Sup3rSecret!',
    department='Electrical and Computer Engineering',
    google_id='GID123',
    orcid='0000-0002-1825-0097',
    scopus_id='7004212771',
)


@pytest.fixture
def reg_env(tmp_path, app):
    """Miniature scaffold template + empty professors root in a temp dir,
    config pointed at them, and a pinned department list — so a successful
    registration really creates a folder, in the temp dir. Cleans up any
    rows the tests created afterwards."""
    tpl = tmp_path / 'template'
    (tpl / 'make_cv' / 'PersonalData').mkdir(parents=True)
    (tpl / 'make_cv' / 'FAR').mkdir(parents=True)
    (tpl / 'make_cv' / 'PersonalData' / 'personal_data.txt').write_text(
        'googleid = \nwebscraperid = \nscopusid = \norcid = \n')
    (tpl / 'make_cv' / 'PersonalData' / 'ContactInfo.tex').write_text(
        '\\mynames{Doe/J}\n')
    (tpl / 'make_cv' / 'FAR' / 'make_cv.cfg').write_text(
        '[CV]\nscopusstats = true\ngooglestats = true\n')

    root = tmp_path / 'Professors'
    root.mkdir()

    app.config['SCAFFOLD_TEMPLATE'] = str(tpl)
    app.config['PROFESSORS_ROOT'] = str(root)
    app.config['DEPARTMENTS'] = [
        'Electrical and Computer Engineering',
        'Computer Science',
    ]
    app.config['INSTITUTION'] = {
        'name': 'Clarkson University',
        'address': '8 Clarkson Ave, Potsdam, NY 13699',
        'email_domain': 'clarkson.edu',
    }

    yield {'template': tpl, 'root': root}

    _cleanup(app)


def _cleanup(app):
    """Remove any rows the tests created, for both the legitimate and the
    outside email (the latter should never exist — but if a bug created
    it, don't leave it polluting the test DB)."""
    with app.app_context():
        for email in (REG_EMAIL, OUTSIDE_EMAIL):
            row = execute_query(
                'SELECT ProfessorKey FROM users WHERE Email=%s',
                (email,), fetchone=True)
            execute_query('DELETE FROM users WHERE Email=%s',
                          (email,), commit=True)
            if row and row.get('ProfessorKey'):
                execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey=%s',
                              (row['ProfessorKey'],), commit=True)


def _rows(app, email=REG_EMAIL):
    """The users row and its linked PROFESSOR row, or (None, None)."""
    with app.app_context():
        u = execute_query('SELECT * FROM users WHERE Email=%s',
                          (email,), fetchone=True)
        p = None
        if u and u.get('ProfessorKey'):
            p = execute_query('SELECT * FROM PROFESSOR WHERE ProfessorKey=%s',
                              (u['ProfessorKey'],), fetchone=True)
        return u, p


# ------------------------------------------------------------------ render

def test_register_page_renders_with_departments(client, reg_env):
    resp = client.get('/register')
    assert resp.status_code == 200
    assert b'Electrical and Computer Engineering' in resp.data
    assert b'Computer Science' in resp.data


# ------------------------------------------------------------- happy path

def test_valid_registration_creates_account_and_folder(app, client, reg_env):
    resp = client.post('/register', data=VALID)

    # Redirects to login (immediate activation — the account works now).
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']

    u, p = _rows(app)
    assert u is not None, 'users row should exist'
    assert u['Role'] == 'professor'
    assert u['Name'] == 'Reg Istrant'

    assert p is not None, 'PROFESSOR row should exist and be linked'
    assert p['FirstName'] == 'Reg'
    assert p['MiddleName'] == 'T'
    assert p['LastName'] == 'Istrant'
    assert p['Department'] == 'Electrical and Computer Engineering'
    assert p['GoogleID'] == 'GID123'
    assert p['ORCID'] == '0000-0002-1825-0097'
    assert p['ScopusID'] == '7004212771'

    # The folder was created through the service, IDs flowed through.
    folder = reg_env['root'] / str(u['ProfessorKey'])
    assert folder.is_dir()
    assert (folder / '.scaffold_version').is_file()
    personal = (folder / 'make_cv' / 'PersonalData'
                / 'personal_data.txt').read_text()
    assert 'scopusid = 7004212771' in personal
    assert 'orcid = 0000-0002-1825-0097' in personal


# -------------------------------------------------------------- rejections

def test_non_clarkson_email_is_rejected(app, client, reg_env):
    resp = client.post('/register', data=dict(VALID, email=OUTSIDE_EMAIL))
    assert resp.status_code == 200          # form re-rendered with errors
    u, _ = _rows(app, email=OUTSIDE_EMAIL)
    assert u is None


def test_duplicate_email_is_rejected(app, client, reg_env, seed_professor):
    resp = client.post('/register',
                       data=dict(VALID, email=seed_professor['email']))
    assert resp.status_code == 200
    with app.app_context():
        rows = execute_query('SELECT UserID FROM users WHERE Email=%s',
                             (seed_professor['email'],))
        assert len(rows) == 1               # the existing account, untouched


def test_department_outside_list_is_rejected(app, client, reg_env):
    resp = client.post('/register',
                       data=dict(VALID, department='Basket Weaving'))
    assert resp.status_code == 200
    u, _ = _rows(app)
    assert u is None


def test_password_mismatch_is_rejected(app, client, reg_env):
    resp = client.post('/register',
                       data=dict(VALID, confirm_password='different'))
    assert resp.status_code == 200
    u, _ = _rows(app)
    assert u is None


# ------------------------------------------------- decoupled folder failure

def test_account_is_created_even_when_folder_creation_fails(app, client,
                                                            reg_env):
    """The core decoupling decision: the account and the folder are two
    operations with different failure modes. A broken template must not
    cost the professor their registration."""
    app.config['SCAFFOLD_TEMPLATE'] = str(reg_env['template']) + '_missing'

    resp = client.post('/register', data=VALID, follow_redirects=True)

    u, p = _rows(app)
    assert u is not None and p is not None   # account exists regardless
    assert not (reg_env['root'] / str(u['ProfessorKey'])).exists()
    assert b'folder' in resp.data.lower()    # non-blocking warning shown
