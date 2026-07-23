"""
Tests for professor folder path resolution (ID-based scheme).

Written BEFORE the get_professor_folder rewrite — these should FAIL (red)
against the current name-based implementation, and pass (green) once the
ID-based scheme lands. That failure is the point: it proves the test is
actually exercising the behavior we're about to change.
"""
import os

from app.routes.generate import get_professor_folder


def _key_of(seeded):
    """Tolerate seed_professor returning either a key or a row dict.
    Adjust to match conftest if needed."""
    if isinstance(seeded, dict):
        return seeded.get('ProfessorKey') or seeded.get('professor_key')
    return seeded


def test_professor_folder_is_id_based(app, seed_professor):
    """The resolved folder is <PROFESSORS_ROOT>/<ProfessorKey> — nothing else."""
    with app.app_context():
        pk = _key_of(seed_professor)
        folder, prof = get_professor_folder(pk)

        assert prof is not None, "professor row should be found"
        root = app.config['PROFESSORS_ROOT']
        assert folder == os.path.join(root, str(pk))


def test_folder_name_contains_no_identity_data(app, seed_professor):
    """The folder name is the bare key: no names, spaces, commas, or
    ampersands — the properties that made the old scheme fragile."""
    with app.app_context():
        pk = _key_of(seed_professor)
        folder, _ = get_professor_folder(pk)
        name = os.path.basename(folder)

        assert name == str(pk)
        for ch in (' ', ',', '&'):
            assert ch not in name


def test_unknown_professor_returns_none_pair(app):
    """Nonexistent key resolves to (None, None), matching the existing
    contract that callers already check."""
    with app.app_context():
        folder, prof = get_professor_folder(999999)
        assert folder is None
        assert prof is None
