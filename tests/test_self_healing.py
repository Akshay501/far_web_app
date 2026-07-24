"""
Tests for folder self-healing (Step 5).

Written BEFORE the implementation. The contract:

  accounts.ensure_folder_for_existing(professor_key)
      -> ('created', None) | ('exists', None) | (None, error_message)
      Gathers the professor's name/email/IDs from the DB and calls the
      folder service. Never raises; unknown professor is an error tuple.

  POST /generate (professor)
      -> a missing folder is healed automatically before prerequisites;
         the old "contact your administrator" dead-end disappears.
         If healing fails, a clear error surfaces (no crash).

  POST /admin/professor/<pk>/create-folder (admin only)
      -> heals on demand: 'created' / already-exists notice / error,
         redirecting back to the professor view. Non-admins are bounced.

Route-level tests stub run_make_far/export_all so they are about the
HEALING, not about LaTeX — folder-creation correctness itself is covered
by the folder-service tests.
"""
import pytest

from app.utils import execute_query


# ---------------------------------------------------------- heal helper

def test_heal_creates_folder_for_existing_professor(app, seed_professor,
                                                    scaffold):
    from app.accounts import ensure_folder_for_existing

    with app.app_context():
        status, err = ensure_folder_for_existing(
            seed_professor['professor_key'])

    assert err is None
    assert status == 'created'
    folder = scaffold['root'] / str(seed_professor['professor_key'])
    assert folder.is_dir()
    assert (folder / '.scaffold_version').is_file()


def test_heal_is_idempotent(app, seed_professor, scaffold):
    from app.accounts import ensure_folder_for_existing

    with app.app_context():
        s1, _ = ensure_folder_for_existing(seed_professor['professor_key'])
        s2, _ = ensure_folder_for_existing(seed_professor['professor_key'])

    assert (s1, s2) == ('created', 'exists')


def test_heal_unknown_professor_returns_error(app, scaffold):
    from app.accounts import ensure_folder_for_existing

    with app.app_context():
        status, err = ensure_folder_for_existing(999999)

    assert status is None
    assert err


def test_heal_reports_template_failure_cleanly(app, seed_professor,
                                               scaffold):
    from app.accounts import ensure_folder_for_existing

    app.config['SCAFFOLD_TEMPLATE'] = str(scaffold['template']) + '_missing'
    with app.app_context():
        status, err = ensure_folder_for_existing(
            seed_professor['professor_key'])

    assert status is None
    assert err
    assert not (scaffold['root']
                / str(seed_professor['professor_key'])).exists()


# --------------------------------------------- generate-route self-healing

def test_generate_heals_missing_folder(app, logged_in_client,
                                       seed_professor, scaffold,
                                       monkeypatch):
    """A professor whose folder was never created (e.g. the decoupled
    attempt failed at registration) generates a report: the folder is
    built automatically, and the old administrator dead-end is gone."""
    import app.routes.generate as gen
    # Keep the test about healing: fail the pipeline cleanly after it.
    monkeypatch.setattr(gen, 'run_make_far',
                        lambda *a, **k: (False, 'stubbed by test'))
    monkeypatch.setattr(gen, 'export_all', lambda *a, **k: None)

    folder = scaffold['root'] / str(seed_professor['professor_key'])
    assert not folder.exists()

    resp = logged_in_client.post('/generate', data={
        'doc_type': 'far', 'years': '1', 'format': 'pdf',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert folder.is_dir(), 'the folder must be healed before generation'
    assert (folder / '.scaffold_version').is_file()
    # The removed dead-end's distinctive wording must never return.
    # (Broader phrases like "contact your administrator" are legitimate
    # translate_error vocabulary and may appear for other reasons.)
    assert b'has not been set up on this server' not in resp.data.lower()


def test_generate_surfaces_heal_failure(app, logged_in_client,
                                        seed_professor, scaffold):
    """If healing itself fails (broken template), the professor gets a
    clear error mentioning the folder — not a crash."""
    app.config['SCAFFOLD_TEMPLATE'] = str(scaffold['template']) + '_missing'

    resp = logged_in_client.post('/generate', data={
        'doc_type': 'far', 'years': '1', 'format': 'pdf',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b'folder' in resp.data.lower()
    assert not (scaffold['root']
                / str(seed_professor['professor_key'])).exists()


# ------------------------------------------------------ admin repair action

def _repair_url(pk):
    return f'/admin/professor/{pk}/create-folder'


def test_admin_repair_creates_folder(app, admin_client, seed_professor,
                                     scaffold):
    resp = admin_client.post(_repair_url(seed_professor['professor_key']),
                             follow_redirects=True)

    assert resp.status_code == 200
    folder = scaffold['root'] / str(seed_professor['professor_key'])
    assert folder.is_dir()
    assert b'created' in resp.data.lower()


def test_admin_repair_reports_existing_folder(app, admin_client,
                                              seed_professor, scaffold):
    admin_client.post(_repair_url(seed_professor['professor_key']))
    resp = admin_client.post(_repair_url(seed_professor['professor_key']),
                             follow_redirects=True)

    assert resp.status_code == 200
    assert b'already' in resp.data.lower()


def test_admin_repair_requires_admin(app, logged_in_client,
                                     seed_professor, scaffold):
    resp = logged_in_client.post(
        _repair_url(seed_professor['professor_key']))

    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
    assert not (scaffold['root']
                / str(seed_professor['professor_key'])).exists()
