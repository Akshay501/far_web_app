"""
Tests for refreshing derived PersonalData files (ContactInfo.tex and
personal_data.txt) from the database.

Both files are generated from the professor's DB record, but until now
were written only inside ensure_professor_folder's creation block. A
folder that predates the folder service — professor 1, migrated during
the ID-path redesign, and every folder to be imported from the s-drive
— therefore kept the scaffold template's placeholders forever:

    Jane U. Doe, Ph.D.
    Somewhere University, Somewhere, XX 16753

That placeholder printed as the header of a real generated CV. It also
affects the FAR, less visibly: ContactInfo supplies \\mynames, which is
what bolds the professor's own name in their publication list.

The contract: these files are DERIVED state, refreshed from the
database on every generation and export — exactly like the Excel files
and scholarship.bib — not written once at creation.
"""
import io
import zipfile
from pathlib import Path

import pytest

from app.utils import execute_query

PLACEHOLDER = (
    '\\mynames{Doe/J}\n'
    '\\leftheader{{\\LARGE Jane U.\\ Doe, Ph.D.}\\\\\n'
    'Somewhere University, Somewhere, XX 16753\\\\\n'
    'myemail@somewhere.edu}\n'
)


@pytest.fixture
def stale_folder(scaffold, seed_professor, app):
    """A professor folder holding the template's placeholder PersonalData
    files — the state every pre-service folder is in. Also gives the
    professor publication IDs in the DB that are absent on disk."""
    folder = scaffold['root'] / str(seed_professor['professor_key'])
    personal = folder / 'make_cv' / 'PersonalData'
    personal.mkdir(parents=True)
    (personal / 'ContactInfo.tex').write_text(PLACEHOLDER)
    (personal / 'personal_data.txt').write_text(
        'googleid = \nwebscraperid = \nscopusid = \norcid = \n')
    (folder / 'Scholarship').mkdir()
    (folder / 'make_cv' / 'FAR').mkdir(parents=True, exist_ok=True)

    with app.app_context():
        execute_query(
            'UPDATE PROFESSOR SET ORCID=%s, ScopusID=%s, GoogleID=%s '
            'WHERE ProfessorKey=%s',
            ('0000-0002-1825-0097', '55555555555', 'GSCHOLARID1',
             seed_professor['professor_key']), commit=True)

    yield folder

    with app.app_context():
        execute_query(
            'UPDATE PROFESSOR SET ORCID=NULL, ScopusID=NULL, GoogleID=NULL '
            'WHERE ProfessorKey=%s',
            (seed_professor['professor_key'],), commit=True)


def _contact(folder):
    return (folder / 'make_cv' / 'PersonalData' / 'ContactInfo.tex').read_text()


def _personal(folder):
    return (folder / 'make_cv' / 'PersonalData' / 'personal_data.txt').read_text()


# ------------------------------------------------------------ the helper

def test_refresh_replaces_placeholder_contactinfo(app, seed_professor,
                                                  stale_folder):
    from app.accounts import refresh_personal_files

    assert 'Jane U.' in _contact(stale_folder)

    with app.app_context():
        ok = refresh_personal_files(seed_professor['professor_key'],
                                    str(stale_folder))

    assert ok
    text = _contact(stale_folder)
    assert 'Jane U.' not in text, 'the placeholder must be gone'
    assert 'Pytest Professor' in text
    assert '\\mynames{Professor/P}' in text, \
        'mynames drives author bolding and must match the professor'
    assert 'pytest.professor@clarkson.edu' in text
    assert 'Clarkson University' in text


def test_refresh_writes_publication_ids(app, seed_professor, stale_folder):
    """The IDs live in the DB but were blank on disk — which would leave
    #9's publication sync with nothing to fetch from."""
    from app.accounts import refresh_personal_files

    with app.app_context():
        refresh_personal_files(seed_professor['professor_key'],
                               str(stale_folder))

    text = _personal(stale_folder)
    assert '0000-0002-1825-0097' in text
    assert '55555555555' in text
    assert 'GSCHOLARID1' in text


def test_refresh_unknown_professor_is_harmless(app, scaffold, tmp_path):
    from app.accounts import refresh_personal_files

    with app.app_context():
        ok = refresh_personal_files(999999, str(tmp_path))

    assert ok is False, 'an unknown professor returns False, never raises'


# ------------------------------------------------------- the refresh paths

def test_generation_refreshes_contactinfo(app, logged_in_client,
                                          seed_professor, stale_folder,
                                          monkeypatch):
    import app.routes.generate as gen
    monkeypatch.setattr(gen, 'run_make_far',
                        lambda *a, **k: (False, 'stubbed by test'))
    monkeypatch.setattr(gen, 'export_all', lambda *a, **k: None)

    logged_in_client.post('/generate', data={
        'doc_type': 'far', 'years': '1', 'format': 'pdf',
    }, follow_redirects=True)

    assert 'Jane U.' not in _contact(stale_folder), \
        'generation must refresh ContactInfo from the database'
    assert 'Pytest Professor' in _contact(stale_folder)


def test_export_zip_carries_refreshed_contactinfo(app, logged_in_client,
                                                  seed_professor,
                                                  stale_folder):
    resp = logged_in_client.post('/professor/export')

    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    name = next(n for n in zf.namelist() if n.endswith('ContactInfo.tex'))
    text = zf.read(name).decode('utf-8')

    assert 'Jane U.' not in text
    assert 'Pytest Professor' in text


# ------------------------------------------- human-authored files are safe

HAND_WRITTEN = (
    '\\mynames{Helenbrook/B}\n'
    '\\leftheader{%\n'
    '  {\\LARGE Brian T. Helenbrook, Ph.D.}\\\\\n'
    '  Clarkson University, Potsdam NY, (315) 268-1234\\\\\n'
    '  bhelenbr@clarkson.edu \\quad LinkedIn \\quad Webpage\n'
    '}\n'
)


def test_hand_edited_contactinfo_is_left_alone(app, seed_professor,
                                               stale_folder):
    """A ContactInfo someone wrote by hand carries details the database
    has no column for — phone, LinkedIn, webpage. Refreshing it would
    destroy real data, so the app must not touch it."""
    from app.accounts import refresh_personal_files

    contact = stale_folder / 'make_cv' / 'PersonalData' / 'ContactInfo.tex'
    contact.write_text(HAND_WRITTEN)

    with app.app_context():
        refresh_personal_files(seed_professor['professor_key'],
                               str(stale_folder))

    assert contact.read_text() == HAND_WRITTEN, \
        'a hand-authored ContactInfo must survive untouched'
    # ...but the key-value IDs file is ours and still refreshes.
    assert '0000-0002-1825-0097' in _personal(stale_folder)


def test_app_written_contactinfo_is_kept_current(app, seed_professor,
                                                 stale_folder):
    """A file the app generated carries its marker, so a later change of
    name or email flows through on the next generation."""
    from app.accounts import refresh_personal_files
    from app.folder_service import CONTACTINFO_MARKER

    with app.app_context():
        refresh_personal_files(seed_professor['professor_key'],
                               str(stale_folder))
        assert CONTACTINFO_MARKER in _contact(stale_folder)

        execute_query('UPDATE PROFESSOR SET LastName=%s WHERE ProfessorKey=%s',
                      ('Renamed', seed_professor['professor_key']), commit=True)
        refresh_personal_files(seed_professor['professor_key'],
                               str(stale_folder))

    try:
        assert 'Pytest Renamed' in _contact(stale_folder)
        assert '\\mynames{Renamed/P}' in _contact(stale_folder)
    finally:
        with app.app_context():
            execute_query(
                'UPDATE PROFESSOR SET LastName=%s WHERE ProfessorKey=%s',
                ('Professor', seed_professor['professor_key']), commit=True)
