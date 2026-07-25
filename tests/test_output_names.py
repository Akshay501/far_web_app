"""
Tests for per-professor output filenames (the far.pdf anonymity issue).

Generated files were always far.pdf / far.docx / cv.pdf — anonymous the
moment they left their zip, and (per the FAR-template finding) the PDF
contents carry no name either. The contract:

  generated_name('far.pdf', 'Thugudam', 'Akshay')
      -> 'far_thugudam_akshay_<date>.pdf'

applied at packaging time only — files ON DISK keep make_cv's names
(far.pdf etc.); renaming there would fight the tool. Only zip entry
names and download names change.
"""
import io
import zipfile
from pathlib import Path

import pytest

from app.routes.generate import generated_name


# ------------------------------------------------------------ pure naming

@pytest.mark.parametrize('base,last,first,expected', [
    ('far.pdf', 'Thugudam', 'Akshay', 'far_thugudam_akshay_20260725.pdf'),
    ('far.docx', 'Thugudam', 'Akshay', 'far_thugudam_akshay_20260725.docx'),
    ('cv.pdf', 'Van Der Berg', 'Anna', 'cv_van_der_berg_anna_20260725.pdf'),
    ('far.pdf', "O'Brien", 'Pat', 'far_obrien_pat_20260725.pdf'),
    ('far.pdf', 'García', 'José', 'far_garcia_jose_20260725.pdf'),
])
def test_generated_name(base, last, first, expected):
    assert generated_name(base, last, first, date_str='20260725') == expected


# ------------------------------------------------------- route-level proof

def test_single_generation_zip_uses_professor_names(
        app, logged_in_client, seed_professor, scaffold, monkeypatch):
    """Generate one FAR (pipeline stubbed to just drop a fake far.pdf):
    the zip entry must carry the professor's name; the anonymous name
    must be gone; the zip download name must be slug-safe."""
    import app.routes.generate as gen

    def fake_make_far(folder, use_pandoc=False):
        Path(folder, 'far.pdf').write_bytes(b'%PDF-fake')
        return True, None

    monkeypatch.setattr(gen, 'run_make_far', fake_make_far)
    monkeypatch.setattr(gen, 'export_all', lambda *a, **k: None)

    resp = logged_in_client.post('/generate', data={
        'doc_type': 'far', 'years': '1', 'format': 'pdf',
    })

    assert resp.status_code == 200
    assert resp.mimetype == 'application/zip'

    names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
    assert len(names) == 1
    # Seeded professor: LastName 'Professor', FirstName 'Pytest'.
    assert names[0].startswith('far_professor_pytest_')
    assert names[0].endswith('.pdf')
    assert 'far.pdf' not in names, 'the anonymous name must be gone'

    disposition = resp.headers.get('Content-Disposition', '')
    assert 'FAR_professor_' in disposition, \
        'the zip download name must use the slug, not the raw last name'
