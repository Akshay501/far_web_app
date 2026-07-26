"""
Tests for password changes (Phase 0.2 — gates real-faculty onboarding,
since admin-generated temporary passwords are currently permanent).

The contract:

  GET  /change-password   -> form, for ANY logged-in user (professors
                             and admins alike; the admin account still
                             ships with a weak default password)
  POST /change-password   -> current password must verify; new password
                             min 8 chars and confirmed; on success the
                             hash changes, the session is dropped
                             (logout_user) and the user signs in again
  anonymous               -> bounced to login

  POST /admin/professor/<pk>/reset-password  (admin only)
      -> generates a temporary password, shown once in the flash, and
         replaces that professor's hash. Non-admins bounced.

Every assertion is against the stored HASH via check_password_hash —
never against a flash message alone, which would pass even if nothing
was written.
"""
import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app.utils import execute_query

NEW_PASSWORD = 'brand-new-pass-99'


def _hash_of(app, user_id):
    with app.app_context():
        row = execute_query('SELECT Password FROM users WHERE UserID = %s',
                            (user_id,), fetchone=True)
        return row['Password'] if row else None


@pytest.fixture
def restore_password(app, seed_professor):
    """The seeded professor's password is changed by these tests; put it
    back so later tests (and reruns) still log in."""
    yield
    with app.app_context():
        execute_query(
            'UPDATE users SET Password = %s WHERE UserID = %s',
            (generate_password_hash(seed_professor['password']),
             seed_professor['user_id']), commit=True)


# ------------------------------------------------------------------ access

def test_change_password_page_renders(logged_in_client, seed_professor):
    resp = logged_in_client.get('/change-password')

    assert resp.status_code == 200
    assert b'urrent' in resp.data          # "Current password" label
    assert resp.data.count(b'type="password"') >= 3


def test_anonymous_is_bounced(client):
    resp = client.get('/change-password')

    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


# ------------------------------------------------------------- happy path

def test_valid_change_updates_the_hash(app, logged_in_client,
                                       seed_professor, restore_password):
    before = _hash_of(app, seed_professor['user_id'])

    resp = logged_in_client.post('/change-password', data={
        'current_password': seed_professor['password'],
        'new_password': NEW_PASSWORD,
        'confirm_password': NEW_PASSWORD,
    }, follow_redirects=True)

    assert resp.status_code == 200
    after = _hash_of(app, seed_professor['user_id'])
    assert after != before
    assert check_password_hash(after, NEW_PASSWORD)
    assert not check_password_hash(after, seed_professor['password'])


def test_change_forces_relogin(app, logged_in_client, seed_professor,
                               restore_password):
    """The session is dropped on change: the old password no longer
    works, the new one does."""
    logged_in_client.post('/change-password', data={
        'current_password': seed_professor['password'],
        'new_password': NEW_PASSWORD,
        'confirm_password': NEW_PASSWORD,
    })

    # Session gone: a professor-only page now redirects to login.
    resp = logged_in_client.get('/professor/dashboard')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']

    # Old password refused, new password accepted.
    old = logged_in_client.post('/login', data={
        'email': seed_professor['email'],
        'password': seed_professor['password']})
    assert '/login' in old.headers.get('Location', '/login')

    new = logged_in_client.post('/login', data={
        'email': seed_professor['email'], 'password': NEW_PASSWORD})
    assert '/login' not in new.headers.get('Location', '')


# -------------------------------------------------------------- rejections

@pytest.mark.parametrize('data,reason', [
    ({'current_password': 'wrong-password',
      'new_password': NEW_PASSWORD,
      'confirm_password': NEW_PASSWORD}, 'wrong current password'),
    ({'current_password': 'pytest123',
      'new_password': NEW_PASSWORD,
      'confirm_password': 'something-else'}, 'confirmation mismatch'),
    ({'current_password': 'pytest123',
      'new_password': 'short',
      'confirm_password': 'short'}, 'too short'),
])
def test_invalid_change_leaves_password_untouched(
        app, logged_in_client, seed_professor, restore_password,
        data, reason):
    before = _hash_of(app, seed_professor['user_id'])

    logged_in_client.post('/change-password', data=data)

    after = _hash_of(app, seed_professor['user_id'])
    assert after == before, f'password must not change on {reason}'
    assert check_password_hash(after, seed_professor['password'])


# ----------------------------------------------------------- admin reset

def _reset_url(pk):
    return f'/admin/professor/{pk}/reset-password'


def test_admin_reset_replaces_the_hash_and_shows_it_once(
        app, admin_client, seed_professor, restore_password):
    before = _hash_of(app, seed_professor['user_id'])

    resp = admin_client.post(_reset_url(seed_professor['professor_key']),
                             follow_redirects=True)

    assert resp.status_code == 200
    after = _hash_of(app, seed_professor['user_id'])
    assert after != before, 'the reset must actually replace the hash'
    assert b'emporary password' in resp.data


def test_non_admin_cannot_reset(app, logged_in_client, seed_professor,
                                restore_password):
    before = _hash_of(app, seed_professor['user_id'])

    resp = logged_in_client.post(
        _reset_url(seed_professor['professor_key']))

    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
    assert _hash_of(app, seed_professor['user_id']) == before
