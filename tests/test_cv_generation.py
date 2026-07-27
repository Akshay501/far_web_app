"""
Tests for CV generation (Issue #8) — removing a dead path that shadowed
a working one.

Two CV paths existed:

  * REAL: POST /generate with doc_type='cv' -> ensure_config_updated ->
    run_make_cv (imports make_cv's main in-process, chdir into the CV
    folder) -> packages cv.pdf with a per-professor filename. Built
    during the make_cv integration; sound.

  * DEAD: the dashboard's "Generate Full CV" button -> GET
    /professor/generate_cv -> app.utils.generate_cv, which shelled out
    to '../make_cv/make_cv.py' (a path that does not exist — make_cv is
    an installed package), passed a ProfessorKey as a CLI argument, and
    on "success" returned a HARDCODED path to a file it never wrote.
    Pre-integration archaeology. It always failed, and the route turned
    the failure into "CV generation failed" with no reason logged.

The dashboard pointed at the dead one, so the working feature was
unreachable in practice. These tests pin the removal and the real path.
"""
import io
import zipfile
from pathlib import Path

import pytest


# ------------------------------------------------------- the dead path is gone

def test_legacy_cv_route_is_removed(logged_in_client, seed_professor):
    resp = logged_in_client.get('/professor/generate_cv')

    assert resp.status_code == 404, \
        'the pre-integration CV route must no longer exist'


def test_legacy_generate_cv_helper_is_removed():
    import app.utils as utils

    assert not hasattr(utils, 'generate_cv'), \
        'the dead subprocess helper must be gone from utils'


def test_dashboard_points_at_the_real_generate_page(logged_in_client,
                                                    seed_professor):
    resp = logged_in_client.get('/professor/dashboard')

    assert resp.status_code == 200
    assert b'/professor/generate_cv' not in resp.data, \
        'the dashboard must not link to the removed route'
    assert b'/generate' in resp.data, \
        'the dashboard should send the professor to the generate page'


# --------------------------------------------------------- the real path works

def test_cv_generation_packages_a_named_file(app, logged_in_client,
                                             seed_professor, scaffold,
                                             monkeypatch):
    """POST /generate with doc_type='cv' runs the real CV branch (make_cv
    itself stubbed) and packages cv.pdf under a per-professor name."""
    import app.routes.generate as gen

    def fake_make_cv(cv_folder):
        Path(cv_folder, 'cv.pdf').write_bytes(b'%PDF-fake-cv')
        return True, None

    monkeypatch.setattr(gen, 'run_make_cv', fake_make_cv)
    monkeypatch.setattr(gen, 'ensure_config_updated', lambda *a, **k: None)
    monkeypatch.setattr(gen, 'export_all', lambda *a, **k: None)

    resp = logged_in_client.post('/generate', data={
        'doc_type': 'cv', 'years': '1', 'format': 'pdf',
    })

    assert resp.status_code == 200
    assert resp.mimetype == 'application/zip'

    names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
    assert len(names) == 1
    # Seeded professor: LastName 'Professor', FirstName 'Pytest'.
    assert names[0].startswith('cv_professor_pytest_')
    assert names[0].endswith('.pdf')
    assert 'cv.pdf' not in names, 'the anonymous name must not survive'
