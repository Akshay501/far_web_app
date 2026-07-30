"""
Issue #9, slice (a): ORCID publication sync — fetch, dedup, and a
review page. Accepting candidates into the database is slice (b); this
slice ends at a rendered review screen that has committed nothing.

Design (revised after reading bib_get_entries_orcid.py in full):

  We do NOT call the top-level bib_get_entries_orcid: it Y/N-prompts
  per entry unless make_cv's module-global quiet flag is flipped
  (global state in a server — and quiet mode auto-accepts entries with
  no review), it runs BibtexAutocomplete's third-party lookups per
  entry, and it writes a .bib file when what we need is candidates in
  memory. Instead the sync service
  calls the small helpers directly (get_all_works, get_work,
  bibtex_entry) and dedups against OUR database, which is the source of
  truth — scholarship.bib is regenerated from it on every run.

  Dedup keys, both taken from what the DB already stores:
    - DOI (exact, case-insensitive) — the strong key
    - title+year via make_cv's make_title_id — the fallback when a
      fetched work has no DOI

  Every fetch has a hard timeout and the service is its own explicit
  action, never part of the generate path (the stats-hang law).

The fetcher is monkeypatched with canned works, so fetch -> dedup ->
stage runs with no network. One live run against a real ORCID is a
manual check at the end of the slice, not part of pytest.
"""
import pytest

from app.utils import execute_query


# A canned ORCID work, in the shape our service's fetcher returns:
# (title, year, doi, raw_bibtex, guessed_category).
def _work(title, year, doi, category='article'):
    key = ''.join(c for c in title.lower() if c.isalnum())[:10]
    raw = (f'@{category}{{{key}{year},\n'
           f'  title = {{{title}}},\n'
           f'  year = {{{year}}},\n'
           + (f'  doi = {{{doi}}},\n' if doi else '')
           + '  author = {A. Researcher}\n}}')
    return {'title': title, 'year': str(year), 'doi': doi,
            'raw_bibtex': raw, 'category': category}


NEW_TITLE = 'A Completely Novel Result In Fluid Dynamics'
DUP_DOI_TITLE = 'Shared Work Matched By DOI'
DUP_TITLE_TITLE = 'Shared Work Matched By Title And Year'


@pytest.fixture
def seeded_pubs(app, seed_professor):
    """Two publications already in the DB — one with a DOI, one without —
    so the service has something real to dedup against."""
    pk = seed_professor['professor_key']
    with app.app_context():
        execute_query(
            'INSERT INTO PUBLICATIONS (ProfessorKey, Title, Year, DOI, '
            'RawBibtex) VALUES (%s,%s,%s,%s,%s)',
            (pk, DUP_DOI_TITLE, 2023, '10.1000/shared.doi',
             '@article{a,title={x}}'), commit=True)
        execute_query(
            'INSERT INTO PUBLICATIONS (ProfessorKey, Title, Year, DOI, '
            'RawBibtex) VALUES (%s,%s,%s,%s,%s)',
            (pk, DUP_TITLE_TITLE, 2022, None,
             '@article{b,title={y}}'), commit=True)
        # The review route reads the ORCID from the PROFESSOR row.
        execute_query(
            'UPDATE PROFESSOR SET ORCID = %s WHERE ProfessorKey = %s',
            ('0000-0000-0000-0000', pk), commit=True)
    yield pk
    with app.app_context():
        execute_query(
            'UPDATE PROFESSOR SET ORCID = NULL WHERE ProfessorKey = %s',
            (pk,), commit=True)
        for t in (NEW_TITLE, DUP_DOI_TITLE, DUP_TITLE_TITLE):
            execute_query('DELETE FROM PUBLICATIONS WHERE Title = %s',
                          (t,), commit=True)


@pytest.fixture
def canned_fetch(monkeypatch):
    """Replace the ORCID fetcher with three works: one genuinely new,
    one duplicating a DB entry by DOI, one duplicating by title+year."""
    import app.publication_sync as sync

    works = [
        _work(NEW_TITLE, 2025, '10.9999/new.one'),
        _work(DUP_DOI_TITLE, 2023, '10.1000/shared.doi'),
        _work(DUP_TITLE_TITLE, 2022, None),
    ]
    monkeypatch.setattr(sync, 'fetch_orcid_works', lambda orcid, years=0: works)
    return works


# --------------------------------------------------------- the service

def test_sync_stages_only_new_works(app, seeded_pubs, canned_fetch):
    """The new work is staged; both duplicates (one by DOI, one by
    title+year) are filtered against the database."""
    from app.publication_sync import find_new_publications

    with app.app_context():
        candidates = find_new_publications(seeded_pubs, '0000-0000-0000-0000')

    titles = [c['title'] for c in candidates]
    assert NEW_TITLE in titles
    assert DUP_DOI_TITLE not in titles, 'DOI match must be deduped'
    assert DUP_TITLE_TITLE not in titles, 'title+year match must be deduped'
    assert len(candidates) == 1


def test_candidate_carries_a_guessed_category(app, seeded_pubs, canned_fetch):
    from app.publication_sync import find_new_publications

    with app.app_context():
        candidates = find_new_publications(seeded_pubs, '0000-0000-0000-0000')

    c = candidates[0]
    assert c.get('category'), 'each candidate needs a guessed category'
    assert c.get('raw_bibtex', '').startswith('@'), \
        'each candidate carries its raw bibtex for later insert'


def test_sync_with_no_orcid_returns_empty(app, seed_professor, monkeypatch):
    """A professor without an ORCID iD yields no candidates and no
    fetch attempt — never an error."""
    import app.publication_sync as sync
    called = []
    monkeypatch.setattr(sync, 'fetch_orcid_works',
                        lambda *a, **k: called.append(1) or [])

    from app.publication_sync import find_new_publications
    with app.app_context():
        candidates = find_new_publications(seed_professor['professor_key'], '')

    assert candidates == []
    assert not called, 'must not fetch when the ORCID iD is blank'


def test_fetch_failure_is_graceful(app, seeded_pubs, monkeypatch):
    """A source that raises (timeout, network error) yields no
    candidates rather than propagating — the stats-hang law."""
    import app.publication_sync as sync

    def boom(*a, **k):
        raise TimeoutError('orcid slow')
    monkeypatch.setattr(sync, 'fetch_orcid_works', boom)

    from app.publication_sync import find_new_publications
    with app.app_context():
        candidates = find_new_publications(seeded_pubs, '0000-0000-0000-0000')

    assert candidates == []


# ------------------------------------------------------- the review page

def test_review_page_requires_login(client):
    resp = client.get('/professor/publications/sync')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_review_page_lists_new_candidates(app, logged_in_client,
                                          seeded_pubs, canned_fetch):
    resp = logged_in_client.get('/professor/publications/sync')

    assert resp.status_code == 200
    assert NEW_TITLE.encode() in resp.data
    # The duplicates must not be offered for import.
    assert DUP_DOI_TITLE.encode() not in resp.data


def test_review_page_when_nothing_new(app, logged_in_client, seed_professor,
                                      monkeypatch):
    """Nothing new to import shows a friendly empty state, not a blank
    table or an error."""
    import app.publication_sync as sync
    monkeypatch.setattr(sync, 'fetch_orcid_works', lambda *a, **k: [])

    resp = logged_in_client.get('/professor/publications/sync')

    assert resp.status_code == 200
    assert (b'up to date' in resp.data.lower()
            or b'no new' in resp.data.lower())
