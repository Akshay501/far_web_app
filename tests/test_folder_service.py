"""
Tests for the professor folder-creation service (Step 3).

Written BEFORE app/folder_service.py exists — the first run should fail on
the import itself. These tests define the contract:

    status = ensure_professor_folder(professor_key, first_name, last_name,
                                     email, google_id=None, orcid=None,
                                     scopus_id=None)
    -> 'created'  (folder built from the scaffold template, files patched)
    -> 'exists'   (folder already present: NEVER touched, never overwritten)
    raises FolderCreationError on failure, after cleaning up any partial copy.

No database is involved: the service takes all identity data as parameters
and touches only the filesystem, so these tests run without MySQL.
"""
import os
import pytest

from app.folder_service import ensure_professor_folder, FolderCreationError


@pytest.fixture
def scaffold(tmp_path, app):
    """A miniature scaffold template + empty professors root in a temp dir,
    with app config pointed at them. Mirrors the real template's shape:
    PersonalData placeholders, stats-enabled cfg files, a .git dir that
    must NOT be copied, and a data file that must be copied verbatim."""
    tpl = tmp_path / 'template'
    (tpl / 'make_cv' / 'PersonalData').mkdir(parents=True)
    (tpl / 'make_cv' / 'FAR').mkdir(parents=True)
    (tpl / 'make_cv' / 'CV').mkdir(parents=True)
    (tpl / 'Scholarship').mkdir()
    (tpl / '.git').mkdir()

    (tpl / '.git' / 'HEAD').write_text('ref: refs/heads/main\n')
    (tpl / 'Scholarship' / 'scholarship.bib').write_text('% template bib\n')
    (tpl / 'make_cv' / 'PersonalData' / 'personal_data.txt').write_text(
        '# Personal data (IDs) for make_cv\n'
        'googleid = \n'
        'webscraperid = \n'
        'scopusid = \n'
        'orcid = \n'
    )
    (tpl / 'make_cv' / 'PersonalData' / 'ContactInfo.tex').write_text(
        '\\mynames{Doe/J}\n'
        '\\leftheader{{\\LARGE Jane U.\\ Doe, Ph.D.}\\\\\n'
        'Somewhere University, Somewhere, XX 16753\\\\\n'
        'myemail@somewhere.edu}\n'
    )
    for sub in ('FAR', 'CV'):
        (tpl / 'make_cv' / sub / 'make_cv.cfg').write_text(
            '[CV]\n'
            'years = 1\n'
            'googlestats = true\n'
            'scopusstats = true\n'
        )

    root = tmp_path / 'Professors'
    root.mkdir()

    app.config['SCAFFOLD_TEMPLATE'] = str(tpl)
    app.config['PROFESSORS_ROOT'] = str(root)
    app.config['INSTITUTION'] = {
        'name': 'Clarkson University',
        'address': '8 Clarkson Ave, Potsdam, NY 13699',
        'email_domain': 'clarkson.edu',
    }
    return {'template': tpl, 'root': root}


def _create(app, **overrides):
    """Call the service with sensible defaults inside an app context."""
    params = dict(
        professor_key=42,
        first_name='Jane',
        last_name='Smith',
        email='jsmith@clarkson.edu',
        google_id='GOOGLE123',
        orcid='0000-0001-2345-6789',
        scopus_id='7004212771',
    )
    params.update(overrides)
    with app.app_context():
        return ensure_professor_folder(**params)


# ---------------------------------------------------------------- creation

def test_creates_folder_from_template(app, scaffold):
    status = _create(app)
    dest = scaffold['root'] / '42'

    assert status == 'created'
    assert dest.is_dir()
    # Scaffolding and data arrive from the template copy.
    assert (dest / 'make_cv' / 'PersonalData' / 'ContactInfo.tex').is_file()
    assert (dest / 'make_cv' / 'FAR' / 'make_cv.cfg').is_file()
    assert (dest / 'Scholarship' / 'scholarship.bib').read_text() == '% template bib\n'


def test_git_dir_is_not_copied(app, scaffold):
    _create(app)
    dest = scaffold['root'] / '42'
    # Professor folders are data, not clones; updates flow through the app.
    assert not (dest / '.git').exists()


# ---------------------------------------------------------------- patching

def test_personal_data_ids_are_written(app, scaffold):
    _create(app)
    text = (scaffold['root'] / '42' / 'make_cv' / 'PersonalData'
            / 'personal_data.txt').read_text()

    assert 'googleid = GOOGLE123' in text
    assert 'orcid = 0000-0001-2345-6789' in text
    assert 'scopusid = 7004212771' in text


def test_personal_data_missing_ids_are_blank(app, scaffold):
    _create(app, google_id=None, orcid=None, scopus_id=None)
    text = (scaffold['root'] / '42' / 'make_cv' / 'PersonalData'
            / 'personal_data.txt').read_text()

    for line in ('googleid =', 'scopusid =', 'orcid ='):
        assert line in text
    assert 'GOOGLE123' not in text


def test_contactinfo_is_patched_for_the_professor(app, scaffold):
    _create(app)
    text = (scaffold['root'] / '42' / 'make_cv' / 'PersonalData'
            / 'ContactInfo.tex').read_text()

    assert '\\mynames{Smith/J}' in text          # biblatex bolding
    assert 'Jane Smith' in text                   # display name
    assert 'Clarkson University' in text          # institution from config
    assert 'jsmith@clarkson.edu' in text          # email
    assert 'Doe' not in text                      # template placeholder gone


def test_contactinfo_escapes_latex_specials_in_names(app, scaffold):
    _create(app, last_name='O\'Brien & Sons')
    text = (scaffold['root'] / '42' / 'make_cv' / 'PersonalData'
            / 'ContactInfo.tex').read_text()

    assert '\\&' in text          # ampersand escaped for LaTeX
    assert ' & ' not in text      # no raw ampersand survives


def test_stats_flags_disabled_in_every_cfg(app, scaffold):
    """Creation-time default: new folders get the institution's known-good
    config (stats off — upstream fetch lacks a timeout and hangs
    generation). Revisit when make_cv ships a fix."""
    _create(app)
    dest = scaffold['root'] / '42'

    for sub in ('FAR', 'CV'):
        cfg = (dest / 'make_cv' / sub / 'make_cv.cfg').read_text()
        assert 'scopusstats = false' in cfg
        assert 'googlestats = false' in cfg
        assert 'scopusstats = true' not in cfg
        assert 'googlestats = true' not in cfg
        assert 'years = 1' in cfg     # untouched keys survive the patch


# ------------------------------------------------------------- idempotency

def test_existing_folder_is_never_touched(app, scaffold):
    dest = scaffold['root'] / '42'
    dest.mkdir()
    sentinel = dest / 'REAL_PROFESSOR_DATA.txt'
    sentinel.write_text('precious')

    status = _create(app)

    assert status == 'exists'
    assert sentinel.read_text() == 'precious'
    # Nothing was copied into the existing folder.
    assert not (dest / 'make_cv').exists()


# ------------------------------------------------------------------ failure

def test_missing_template_fails_cleanly(app, scaffold):
    app.config['SCAFFOLD_TEMPLATE'] = str(scaffold['template']) + '_nope'

    with pytest.raises(FolderCreationError):
        _create(app)

    # No partial folder left behind.
    assert not (scaffold['root'] / '42').exists()
