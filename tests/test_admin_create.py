"""
Tests for the admin add-professor path (Step 4, slice B).

Written BEFORE the route exists — most of these fail with 404s first.
The contract they define:

  GET  /admin/professor/new   -> form for admins (departments from config,
                                 NO password fields — a temporary password
                                 is generated server-side)
  non-admin access            -> bounced to login (admin_required), and a
                                 non-admin POST creates nothing
  POST valid as admin         -> PROFESSOR + users rows via the same
                                 shared creation logic as /register,
                                 folder created, temporary password shown
                                 once in the flash, redirect to the new
                                 professor's admin view
  duplicate email             -> rejected, existing account untouched
  folder creation fails       -> account still created (decoupled),
                                 non-blocking notice mentions the folder

Integration tests against the TEST database; all created rows removed.
"""
import pytest

from app.utils import execute_query

NEW_EMAIL = 'pytest.admincreated@clarkson.edu'

VALID = dict(
    first_name='Admin',
    middle_name='C',
    last_name='Created',
    email=NEW_EMAIL,
    department='Electrical and Computer Engineering',
    google_id='',
    orcid='',
    scopus_id='',
)


@pytest.fixture
def admin_env(scaffold, app):
    """The shared scaffold env plus this file's DB cleanup."""
    yield scaffold
    with app.app_context():
        row = execute_query('SELECT ProfessorKey FROM users WHERE Email=%s',
                            (NEW_EMAIL,), fetchone=True)
        execute_query('DELETE FROM users WHERE Email=%s',
                      (NEW_EMAIL,), commit=True)
        if row and row.get('ProfessorKey'):
            execute_query('DELETE FROM PROFESSOR WHERE ProfessorKey=%s',
                          (row['ProfessorKey'],), commit=True)


def _rows(app, email=NEW_EMAIL):
    with app.app_context():
        u = execute_query('SELECT * FROM users WHERE Email=%s',
                          (email,), fetchone=True)
        p = None
        if u and u.get('ProfessorKey'):
            p = execute_query('SELECT * FROM PROFESSOR WHERE ProfessorKey=%s',
                              (u['ProfessorKey'],), fetchone=True)
        return u, p


# ------------------------------------------------------------------ access

def test_new_professor_page_renders_for_admin(admin_client, admin_env):
    resp = admin_client.get('/admin/professor/new')
    assert resp.status_code == 200
    assert b'Electrical and Computer Engineering' in resp.data
    # No password fields: the temporary password is server-generated.
    assert b'type="password"' not in resp.data


def test_non_admin_is_bounced(logged_in_client, seed_professor, admin_env):
    resp = logged_in_client.get('/admin/professor/new')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_non_admin_post_creates_nothing(app, logged_in_client,
                                        seed_professor, admin_env):
    logged_in_client.post('/admin/professor/new', data=VALID)
    u, _ = _rows(app)
    assert u is None


# ------------------------------------------------------------- happy path

def test_admin_creates_professor_with_folder_and_temp_password(
        app, admin_client, admin_env):
    resp = admin_client.post('/admin/professor/new', data=VALID,
                             follow_redirects=True)
    assert resp.status_code == 200

    u, p = _rows(app)
    assert u is not None and u['Role'] == 'professor'
    assert u['Name'] == 'Admin Created'
    # A real hash was stored (werkzeug prefixes), not a blank.
    assert u['Password'] and u['Password'].startswith(('pbkdf2', 'scrypt'))

    assert p is not None
    assert p['FirstName'] == 'Admin'
    assert p['MiddleName'] == 'C'
    assert p['LastName'] == 'Created'
    assert p['Department'] == 'Electrical and Computer Engineering'

    # Folder created through the shared service, with the version stamp.
    folder = admin_env['root'] / str(u['ProfessorKey'])
    assert folder.is_dir()
    assert (folder / '.scaffold_version').is_file()

    # The one-time temporary password notice reached the admin.
    assert b'emporary password' in resp.data


# -------------------------------------------------------------- rejections

def test_duplicate_email_is_rejected(app, admin_client, admin_env,
                                     seed_professor):
    resp = admin_client.post('/admin/professor/new',
                             data=dict(VALID, email=seed_professor['email']))
    assert resp.status_code == 200
    with app.app_context():
        rows = execute_query('SELECT UserID FROM users WHERE Email=%s',
                             (seed_professor['email'],))
        assert len(rows) == 1


# ------------------------------------------------- decoupled folder failure

def test_account_created_even_when_folder_fails(app, admin_client,
                                                admin_env):
    app.config['SCAFFOLD_TEMPLATE'] = str(admin_env['template']) + '_missing'

    resp = admin_client.post('/admin/professor/new', data=VALID,
                             follow_redirects=True)

    u, p = _rows(app)
    assert u is not None and p is not None
    assert not (admin_env['root'] / str(u['ProfessorKey'])).exists()
    assert b'folder' in resp.data.lower()
