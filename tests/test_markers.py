"""
Tests for the per-author student-marker editor.

These encode, as automated checks, exactly what was verified by hand:
marking an author as a graduate student must store a \\gs prefix in the
publication's RawBibtex, which is what make_cv reads to render the marker.

Place this file at: tests/test_markers.py
"""
import pytest

from app.utils import execute_query


def _stored_bibtex(app, pub_id):
    """Read a publication's RawBibtex straight from the test database."""
    with app.app_context():
        row = execute_query(
            'SELECT RawBibtex, Authors FROM PUBLICATIONS WHERE PublicationKey=%s',
            (pub_id,), fetchone=True
        )
    return row


def _edit_form(pub, author_names, author_markers):
    """Build the publications edit POST body."""
    return {
        'action': 'edit',
        'pub_id': pub['id'],
        'bibkey': pub['bibkey'],
        'type': 'article',
        'keywords': 'journal',
        'title': 'A Sample Publication For Testing',
        'year': '2025',
        'journal': 'Journal of Testing',
        'booktitle': '',
        'volume': '',
        'issue': '',
        'pages': '',
        'doi': '',
        'url': '',
        'publisher': '',
        'author_names[]': author_names,
        'author_markers[]': author_markers,
    }


def test_marking_author_as_graduate_stores_gs(app, logged_in_client, seed_publication):
    """
    Marking the second author as a graduate student should write
    '\\gs Bob Jones' into the stored RawBibtex.
    """
    logged_in_client.post('/professor/publications', data=_edit_form(
        seed_publication,
        author_names=['Alice Smith', 'Bob Jones'],
        author_markers=['none', 'gs'],
    ))

    row = _stored_bibtex(app, seed_publication['id'])
    assert row is not None, 'publication disappeared after edit'
    assert '\\gs Bob Jones' in row['RawBibtex']
    # The unmarked author must NOT pick up a marker.
    assert '\\gs Alice Smith' not in row['RawBibtex']


def test_marking_author_as_undergraduate_stores_us(app, logged_in_client, seed_publication):
    """Marking an author as undergraduate should write '\\us' instead."""
    logged_in_client.post('/professor/publications', data=_edit_form(
        seed_publication,
        author_names=['Alice Smith', 'Bob Jones'],
        author_markers=['us', 'none'],
    ))

    row = _stored_bibtex(app, seed_publication['id'])
    assert '\\us Alice Smith' in row['RawBibtex']


def test_display_authors_have_no_markers(app, logged_in_client, seed_publication):
    """
    The Authors column is the human-readable version and should stay
    marker-free, even when RawBibtex carries markers.
    """
    logged_in_client.post('/professor/publications', data=_edit_form(
        seed_publication,
        author_names=['Alice Smith', 'Bob Jones'],
        author_markers=['none', 'gs'],
    ))

    row = _stored_bibtex(app, seed_publication['id'])
    assert '\\gs' not in (row['Authors'] or '')
    assert 'Bob Jones' in (row['Authors'] or '')


def test_latex_accent_in_author_name_is_not_double_escaped(
        app, logged_in_client, seed_publication):
    """
    An author name containing a LaTeX accent must survive a save unchanged.
    Typing "Jos\\'e Garcia" should stay "Jos\\'e Garcia", not become
    "Jos\\\\'e Garcia" (which LaTeX reads as a line break, not an accent).
    """
    logged_in_client.post('/professor/publications', data=_edit_form(
        seed_publication,
        author_names=["Jos\\'e Garcia", 'Bob Jones'],
        author_markers=['gs', 'none'],
    ))

    row = _stored_bibtex(app, seed_publication['id'])
    assert "Jos\\'e Garcia" in row['RawBibtex']
    assert "Jos\\\\'e Garcia" not in row['RawBibtex']
