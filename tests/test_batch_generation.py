"""
Batch generation hardening (Phase 0.2).

The admin batch loop drifted behind the single-generation route. Three
gaps, found while wiring the ContactInfo refresh:

1. THE CORRECTNESS HOLE — the bib is never refreshed. The single route
   calls write_bib_from_db so that publications edited on the web page
   reach the FAR. The batch loop skips it, so a batch-generated FAR is
   built from whatever scholarship.bib happens to sit on disk — missing
   every publication added through the app since that professor last
   generated individually, including everything the ORCID sync imports.

2. No self-healing. A missing folder is reported as "folder not found"
   and skipped, where the single route heals it and carries on. An
   admin generating twenty FARs should not get holes for professors who
   simply never logged in.

3. Silent gaps in the results table. If run_make_far reports success but
   the PDF is not on disk, no row is appended at all — the professor
   vanishes from the report rather than being listed as failed. The
   docx branch never appends a failure row either.

Every professor must appear in the results exactly once, whatever
happened to them. An admin reading that table needs to be able to trust
that a name missing from it means something is wrong with the report,
not with a professor.
"""
import os

import pytest

from app.utils import execute_query


@pytest.fixture
def batch_stubs(monkeypatch):
    """Neutralise the expensive parts of a batch run and record what the
    loop did. make_far is stubbed to fail: these tests are about the
    refresh/heal/report behaviour around generation, not generation."""
    import app.routes.generate as gen

    calls = {'bib': [], 'heal': [], 'personal': [], 'export': []}

    monkeypatch.setattr(gen, 'write_bib_from_db',
                        lambda pk, folder: calls['bib'].append(pk))
    monkeypatch.setattr(gen, 'refresh_personal_files',
                        lambda pk, folder: calls['personal'].append(pk))
    monkeypatch.setattr(gen, 'fetch_all_db_data', lambda pk: {})
    monkeypatch.setattr(gen, 'export_all',
                        lambda pk, folder, data: calls['export'].append(pk))
    monkeypatch.setattr(gen, 'run_make_far',
                        lambda *a, **k: (False, 'stubbed by test'))
    if hasattr(gen, 'ensure_folder_for_existing'):
        real = gen.ensure_folder_for_existing
        monkeypatch.setattr(
            gen, 'ensure_folder_for_existing',
            lambda pk: calls['heal'].append(pk) or real(pk))
    return calls


def test_batch_refreshes_the_bib_from_the_database(app, admin_client,
                                                   seed_professor, scaffold,
                                                   batch_stubs):
    """THE correctness hole: without this, a batch FAR silently omits
    every publication added through the web app."""
    admin_client.post('/admin/generate-all',
                      data={'years': '1', 'format': 'pdf'})

    assert seed_professor['professor_key'] in batch_stubs['bib'], \
        'batch generation must rebuild scholarship.bib from the database'


def test_batch_refreshes_personal_files(app, admin_client, seed_professor,
                                        scaffold, batch_stubs):
    admin_client.post('/admin/generate-all',
                      data={'years': '1', 'format': 'pdf'})

    assert seed_professor['professor_key'] in batch_stubs['personal']


def test_batch_heals_a_missing_folder(app, admin_client, seed_professor,
                                      scaffold, batch_stubs):
    """A professor who never logged in has no folder. The single route
    heals that; batch must too, rather than reporting a hole."""
    pk = seed_professor['professor_key']
    folder = scaffold['root'] / str(pk)

    resp = admin_client.post('/admin/generate-all',
                             data={'years': '1', 'format': 'pdf'},
                             follow_redirects=True)

    assert resp.status_code == 200
    assert os.path.isdir(folder), \
        'batch must create a missing professor folder, not skip it'
    assert b'folder not found' not in resp.data


def test_every_professor_appears_in_the_results(app, admin_client,
                                                seed_professor, scaffold,
                                                batch_stubs):
    """No silent gaps: make_far is stubbed to fail, so the seeded
    professor must appear as a failure — not vanish from the table."""
    resp = admin_client.post('/admin/generate-all',
                             data={'years': '1', 'format': 'pdf'},
                             follow_redirects=True)

    assert resp.status_code == 200
    assert b'Pytest' in resp.data, \
        'a professor whose generation failed must still be listed'
    assert b'stubbed by test' in resp.data, \
        'the failure reason must be shown, not swallowed'


def test_docx_failures_are_reported_too(app, admin_client, seed_professor,
                                        scaffold, batch_stubs):
    """The docx branch previously appended nothing on failure, so a
    docx-only run could report an empty table while nothing worked."""
    resp = admin_client.post('/admin/generate-all',
                             data={'years': '1', 'format': 'docx'},
                             follow_redirects=True)

    assert resp.status_code == 200
    assert b'Pytest' in resp.data, \
        'a docx failure must appear in the results table'


def test_one_professor_failing_does_not_abort_the_batch(app, admin_client,
                                                        seed_professor,
                                                        scaffold,
                                                        monkeypatch):
    """An exception raised while handling one professor must not take
    down the whole run — the remaining professors still get processed."""
    import app.routes.generate as gen

    monkeypatch.setattr(gen, 'refresh_personal_files',
                        lambda pk, folder: (_ for _ in ()).throw(
                            RuntimeError('boom')))
    monkeypatch.setattr(gen, 'write_bib_from_db', lambda pk, folder: None)
    monkeypatch.setattr(gen, 'fetch_all_db_data', lambda pk: {})
    monkeypatch.setattr(gen, 'export_all', lambda pk, folder, data: None)
    monkeypatch.setattr(gen, 'run_make_far', lambda *a, **k: (False, 'x'))

    resp = admin_client.post('/admin/generate-all',
                             data={'years': '1', 'format': 'pdf'},
                             follow_redirects=True)

    assert resp.status_code == 200, 'the batch must not 500'
    assert b'Pytest' in resp.data, \
        'the failing professor must be listed with their error'


def test_batch_disarms_the_stats_fetch(app, admin_client, seed_professor,
                                       scaffold, batch_stubs):
    """The stats fetch (per-publication citation scraping, no timeout
    upstream) is gated by GoogleStats/ScopusStats in make_cv.cfg. An old
    cfg can arrive armed — and ensure_config_updated's repair step
    re-arms it, because make_cv's create_config defaults those keys to
    TRUE. One armed folder stalls the whole batch; batch must therefore
    disarm after every config update. Observed live 2026-07-30."""
    pk = seed_professor['professor_key']
    far = scaffold['root'] / str(pk) / 'make_cv' / 'FAR'
    far.mkdir(parents=True, exist_ok=True)
    (far / 'make_cv.cfg').write_text(
        '[CV]\n'
        'years = 1\n'
        'GoogleStats = true\n'
        'ScopusStats = true\n')

    admin_client.post('/admin/generate-all',
                      data={'years': '1', 'format': 'pdf'})

    cfg = (far / 'make_cv.cfg').read_text().lower()
    assert 'googlestats = false' in cfg, cfg
    assert 'scopusstats = false' in cfg, cfg
