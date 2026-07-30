"""
Issue #9, slice (a) — ORCID sync with HONEST reporting.

The first version returned only a list of candidates, which made two
very different situations look identical on the page:

    "I checked everything and found nothing new"     -> "up to date"
    "The fetch crashed and I checked nothing at all" -> "up to date"

A green light that might mean "broken" is worse than no light. So
find_new_publications now returns a small REPORT, not just a list:

    {'candidates': [...],      # the new works, as before
     'total_works': int|None,  # how many works the ORCID record holds
     'examined': int,          # how many we actually fetched details for
     'truncated': bool,        # stopped at the work cap / time budget
     'error': None|str}        # human-readable failure, if any

and the page renders three honest states: up to date (with the count),
truncated (checked X of Y), or failed (nothing was checked — try
again). Failure must never be dressed as success.

Also fixed here: the title dedup key now decodes LaTeX before
normalizing (make_cv's make_title_id recipe, verbatim), so a database
title holding "$\\omega$" and an ORCID title holding "ω" produce the
same key. The first live run proved this matters: a real paper was
offered as "new" because the two forms didn't match.

The fetcher is monkeypatched throughout — no network in these tests.
"""
import pytest

from app.utils import execute_query


def _work(title, year, doi, category='article'):
    key = ''.join(c for c in title.lower() if c.isalnum())[:10]
    raw = (f'@{category}{{{key}{year},\n'
           f'  title = {{{title}}},\n'
           f'  year = {{{year}}},\n'
           + (f'  doi = {{{doi}}},\n' if doi else '')
           + '  author = {A. Researcher}\n}')
    return {'title': title, 'year': str(year), 'doi': doi,
            'raw_bibtex': raw, 'category': category}


def _fetch_result(works, total=None, truncated=False):
    """The dict fetch_orcid_works now returns."""
    return {'works': works, 'total': total if total is not None else len(works),
            'examined': len(works), 'truncated': truncated}


NEW_TITLE = 'A Completely Novel Result In Fluid Dynamics'
DUP_DOI_TITLE = 'Shared Work Matched By DOI'
DUP_TITLE_TITLE = 'Shared Work Matched By Title And Year'


@pytest.fixture
def seeded_pubs(app, seed_professor):
    """Two publications already in the DB — one with a DOI, one without —
    plus an ORCID iD on the professor row (the route reads it)."""
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
    """One genuinely new work + one DOI duplicate + one title duplicate."""
    import app.publication_sync as sync

    works = [
        _work(NEW_TITLE, 2025, '10.9999/new.one'),
        _work(DUP_DOI_TITLE, 2023, '10.1000/shared.doi'),
        _work(DUP_TITLE_TITLE, 2022, None),
    ]
    monkeypatch.setattr(sync, 'fetch_orcid_works',
                        lambda orcid, years=0: _fetch_result(works))
    return works


# ------------------------------------------------------- the title key

@pytest.mark.parametrize('a,b', [
    (('Modified k-$\\omega$ Model', 2019), ('Modified k-\u03c9 Model', 2019)),
    (("Work of Jos\\'e Garcia", 2020), ('Work of Jos\u00e9 Garcia', 2020)),
    (('{H}igh-{O}rder Methods!', 2021), ('high order methods', 2021)),
])
def test_title_key_decodes_latex_before_normalizing(a, b):
    """The dedup key must be identical whether a title arrives as LaTeX
    (from a .bib) or plain unicode (from ORCID). This is the exact
    failure the first live run exposed."""
    from app.publication_sync import _title_key

    assert _title_key(*a) == _title_key(*b)


# --------------------------------------------------------- the service

def test_sync_stages_only_new_works(app, seeded_pubs, canned_fetch):
    from app.publication_sync import find_new_publications

    with app.app_context():
        result = find_new_publications(seeded_pubs, '0000-0000-0000-0000')

    titles = [c['title'] for c in result['candidates']]
    assert titles == [NEW_TITLE]
    assert result['error'] is None


def test_result_reports_what_was_examined(app, seeded_pubs, canned_fetch):
    from app.publication_sync import find_new_publications

    with app.app_context():
        result = find_new_publications(seeded_pubs, '0000-0000-0000-0000')

    assert result['total_works'] == 3
    assert result['examined'] == 3
    assert result['truncated'] is False


def test_truncation_is_reported(app, seeded_pubs, monkeypatch):
    """97 works, only 60 examined: the report must say so, so the page
    can stop implying completeness."""
    import app.publication_sync as sync
    monkeypatch.setattr(
        sync, 'fetch_orcid_works',
        lambda orcid, years=0: {'works': [_work(NEW_TITLE, 2025, None)],
                                'total': 97, 'examined': 60,
                                'truncated': True})
    from app.publication_sync import find_new_publications

    with app.app_context():
        result = find_new_publications(seeded_pubs, '0000-0000-0000-0000')

    assert result['total_works'] == 97
    assert result['examined'] == 60
    assert result['truncated'] is True


def test_fetch_failure_is_an_error_not_an_empty_success(app, seeded_pubs,
                                                        monkeypatch):
    """THE core honesty test at the service level: a crash must come
    back labelled as an error, never as a clean empty result."""
    import app.publication_sync as sync

    def boom(*a, **k):
        raise TimeoutError('orcid unreachable')
    monkeypatch.setattr(sync, 'fetch_orcid_works', boom)
    from app.publication_sync import find_new_publications

    with app.app_context():
        result = find_new_publications(seeded_pubs, '0000-0000-0000-0000')

    assert result['candidates'] == []
    assert result['error'], 'a failed fetch must be reported, not hidden'
    assert result['examined'] == 0


def test_sync_with_no_orcid_does_not_fetch(app, seed_professor, monkeypatch):
    import app.publication_sync as sync
    called = []
    monkeypatch.setattr(sync, 'fetch_orcid_works',
                        lambda *a, **k: called.append(1) or _fetch_result([]))
    from app.publication_sync import find_new_publications

    with app.app_context():
        result = find_new_publications(seed_professor['professor_key'], '')

    assert result['candidates'] == []
    assert result['error'] is None
    assert not called


# ------------------------------------------------------------ the page

def test_review_page_requires_login(client):
    resp = client.get('/professor/publications/sync')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_review_page_lists_new_candidates(app, logged_in_client,
                                          seeded_pubs, canned_fetch):
    resp = logged_in_client.get('/professor/publications/sync')

    assert resp.status_code == 200
    assert NEW_TITLE.encode() in resp.data
    assert DUP_DOI_TITLE.encode() not in resp.data


def test_page_up_to_date_states_the_count(app, logged_in_client,
                                          seeded_pubs, monkeypatch):
    import app.publication_sync as sync
    monkeypatch.setattr(sync, 'fetch_orcid_works',
                        lambda orcid, years=0: _fetch_result(
                            [], total=42, truncated=False))
    # make 'examined' meaningful for the empty case
    monkeypatch.setattr(
        sync, 'fetch_orcid_works',
        lambda orcid, years=0: {'works': [], 'total': 42, 'examined': 42,
                                'truncated': False})

    resp = logged_in_client.get('/professor/publications/sync')

    assert resp.status_code == 200
    assert b'up to date' in resp.data.lower()
    assert b'42' in resp.data, 'the all-clear must say how much it checked'


def test_page_admits_truncation(app, logged_in_client, seeded_pubs,
                                monkeypatch):
    import app.publication_sync as sync
    monkeypatch.setattr(
        sync, 'fetch_orcid_works',
        lambda orcid, years=0: {'works': [_work(NEW_TITLE, 2025, None)],
                                'total': 97, 'examined': 60,
                                'truncated': True})

    resp = logged_in_client.get('/professor/publications/sync')

    assert resp.status_code == 200
    assert b'60' in resp.data and b'97' in resp.data, \
        'a truncated check must state what it covered'


def test_page_shows_failure_as_failure(app, logged_in_client, seeded_pubs,
                                       monkeypatch):
    """THE core honesty test at the page level: when the fetch fails,
    the page must say so — and must NOT say "up to date"."""
    import app.publication_sync as sync

    def boom(*a, **k):
        raise TimeoutError('orcid unreachable')
    monkeypatch.setattr(sync, 'fetch_orcid_works', boom)

    resp = logged_in_client.get('/professor/publications/sync')

    assert resp.status_code == 200
    lower = resp.data.lower()
    assert (b'could not' in lower or b'try again' in lower)
    assert b'up to date' not in lower, \
        'a failed check must never be dressed as success'
