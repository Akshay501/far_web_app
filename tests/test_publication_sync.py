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
OTHER_TITLE = 'Another Unimported Result Entirely'
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
        for t in (NEW_TITLE, OTHER_TITLE, DUP_DOI_TITLE, DUP_TITLE_TITLE):
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
                        lambda orcid, years=0, offset=0: _fetch_result(works))
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
        lambda orcid, years=0, offset=0: {'works': [_work(NEW_TITLE, 2025, None)],
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
                        lambda orcid, years=0, offset=0: _fetch_result(
                            [], total=42, truncated=False))
    # make 'examined' meaningful for the empty case
    monkeypatch.setattr(
        sync, 'fetch_orcid_works',
        lambda orcid, years=0, offset=0: {'works': [], 'total': 42, 'examined': 42,
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
        lambda orcid, years=0, offset=0: {'works': [_work(NEW_TITLE, 2025, None)],
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


# ----------------------------------------------- slice (b): the import

def _import_form(*cands, ticked=None):
    """Build the POST body the review page's form produces: hidden
    fields per candidate, checkboxes selecting which to import."""
    form = {}
    for i, c in enumerate(cands):
        form[f'candidate-{i}-raw'] = c['raw_bibtex']
        form[f'candidate-{i}-category'] = c.get('category', 'journal')
    form['import'] = [str(i) for i in (ticked if ticked is not None
                                       else range(len(cands)))]
    return form


def test_import_requires_login(client):
    resp = client.post('/professor/publications/sync/import', data={})
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_import_inserts_selected_candidate(app, logged_in_client,
                                           seeded_pubs):
    """A ticked candidate becomes a real PUBLICATIONS row, owned by the
    logged-in professor, with its RawBibtex stored."""
    cand = _work(NEW_TITLE, 2025, '10.9999/new.one')
    resp = logged_in_client.post('/professor/publications/sync/import',
                                 data=_import_form(cand),
                                 follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        row = execute_query(
            'SELECT ProfessorKey, Title, Year, RawBibtex FROM PUBLICATIONS '
            'WHERE Title = %s', (NEW_TITLE,), fetchone=True)
    assert row, 'the imported candidate must exist in the database'
    assert row['ProfessorKey'] == seeded_pubs
    assert NEW_TITLE in row['RawBibtex']


def test_import_only_inserts_ticked(app, logged_in_client, seeded_pubs):
    """Two candidates in the form, one checkbox ticked: exactly one row."""
    a = _work(NEW_TITLE, 2025, '10.9999/new.one')
    b = _work(OTHER_TITLE, 2024, '10.9999/other.two')
    logged_in_client.post('/professor/publications/sync/import',
                          data=_import_form(a, b, ticked=[0]),
                          follow_redirects=True)

    with app.app_context():
        got_a = execute_query('SELECT 1 FROM PUBLICATIONS WHERE Title=%s',
                              (NEW_TITLE,), fetchone=True)
        got_b = execute_query('SELECT 1 FROM PUBLICATIONS WHERE Title=%s',
                              (OTHER_TITLE,), fetchone=True)
    assert got_a and not got_b


def test_import_rechecks_duplicates_at_insert_time(app, logged_in_client,
                                                   seeded_pubs):
    """The stale-tab case: a candidate that entered the database AFTER
    the review page was rendered must be skipped, not duplicated. The
    dedup runs again at insert time against fresh state."""
    with app.app_context():
        execute_query(
            'INSERT INTO PUBLICATIONS (ProfessorKey, Title, Year, DOI, '
            'RawBibtex) VALUES (%s,%s,%s,%s,%s)',
            (seeded_pubs, NEW_TITLE, 2025, '10.9999/new.one',
             '@article{x,title={z}}'), commit=True)

    cand = _work(NEW_TITLE, 2025, '10.9999/new.one')
    logged_in_client.post('/professor/publications/sync/import',
                          data=_import_form(cand), follow_redirects=True)

    with app.app_context():
        rows = execute_query(
            'SELECT 1 FROM PUBLICATIONS WHERE ProfessorKey=%s AND DOI=%s',
            (seeded_pubs, '10.9999/new.one'))
    assert len(rows) == 1, 'a now-known candidate must be skipped, not doubled'


def test_import_writes_the_chosen_category_keyword(app, logged_in_client,
                                                   seeded_pubs):
    """The category picked on the review screen is written INTO the
    stored bibtex as a keywords line — that is how make_cv decides which
    FAR/CV section the paper lands in when the bib regenerates."""
    cand = _work(NEW_TITLE, 2025, '10.9999/new.one')
    cand['category'] = 'refereed'
    logged_in_client.post('/professor/publications/sync/import',
                          data=_import_form(cand), follow_redirects=True)

    with app.app_context():
        row = execute_query(
            'SELECT Keywords, RawBibtex FROM PUBLICATIONS WHERE Title = %s',
            (NEW_TITLE,), fetchone=True)
    assert row
    assert 'refereed' in (row['Keywords'] or '')
    assert 'keywords' in row['RawBibtex'].lower()
    assert 'refereed' in row['RawBibtex']


def test_import_ignores_smuggled_professor_key(app, logged_in_client,
                                               seeded_pubs):
    """Ownership comes from the session, never from the form."""
    cand = _work(NEW_TITLE, 2025, '10.9999/new.one')
    form = _import_form(cand)
    form['professor_key'] = '999999'
    logged_in_client.post('/professor/publications/sync/import',
                          data=form, follow_redirects=True)

    with app.app_context():
        row = execute_query(
            'SELECT ProfessorKey FROM PUBLICATIONS WHERE Title = %s',
            (NEW_TITLE,), fetchone=True)
    assert row and row['ProfessorKey'] == seeded_pubs




# =====================================================================
# Slice (c): pagination + navigation
#
# The truncation message used to say "run the sync again later for the
# rest" — a white lie, since a second run re-fetched the same first 60
# works. Now the URL carries ?offset=N, the report says which window it
# covered (works 61-97), and the page offers a real continue link. The
# sync page also finally gets a button on the publications page instead
# of being reachable only by typing the URL.
# =====================================================================

def test_service_passes_offset_and_reports_it(app, monkeypatch):
    """DB-free: find_new_publications hands the offset to the fetcher
    and echoes it in the report, so the page can render the window."""
    import app.publication_sync as sync
    seen = {}
    monkeypatch.setattr(sync, 'execute_query', lambda *a, **k: [])

    def fake_fetch(orcid, years=0, offset=0):
        seen['offset'] = offset
        return {'works': [], 'total': 97, 'examined': 37,
                'truncated': False, 'offset': offset}
    monkeypatch.setattr(sync, 'fetch_orcid_works', fake_fetch)

    with app.app_context():
        result = sync.find_new_publications(9001, '0000-0000-0000-0000',
                                            offset=60)

    assert seen['offset'] == 60, 'the fetcher must receive the offset'
    assert result['offset'] == 60, 'the report must echo the offset'


def test_route_reads_offset_and_page_shows_the_window(app, logged_in_client,
                                                      seeded_pubs,
                                                      monkeypatch):
    """?offset=60 reaches the fetch, and the page states works 61-97."""
    import app.publication_sync as sync
    seen = {}

    def fake_fetch(orcid, years=0, offset=0):
        seen['offset'] = offset
        return {'works': [], 'total': 97, 'examined': 37,
                'truncated': False, 'offset': offset}
    monkeypatch.setattr(sync, 'fetch_orcid_works', fake_fetch)

    resp = logged_in_client.get('/professor/publications/sync?offset=60')

    assert resp.status_code == 200
    assert seen.get('offset') == 60
    assert b'61' in resp.data and b'97' in resp.data, \
        'the page must state which window was checked'


def test_truncated_page_offers_a_real_continue_link(app, logged_in_client,
                                                    seeded_pubs,
                                                    monkeypatch):
    """A truncated run links to the NEXT window instead of advising a
    rerun that would repeat the same works."""
    import app.publication_sync as sync
    monkeypatch.setattr(
        sync, 'fetch_orcid_works',
        lambda orcid, years=0, offset=0: {
            'works': [_work(NEW_TITLE, 2025, None)],
            'total': 97, 'examined': 60, 'truncated': True,
            'offset': offset})

    resp = logged_in_client.get('/professor/publications/sync')

    assert resp.status_code == 200
    assert b'offset=60' in resp.data, \
        'the continue link must carry the next offset'


def test_publications_page_links_to_sync(app, logged_in_client, seeded_pubs):
    """The sync page must be reachable by button, not only by URL."""
    resp = logged_in_client.get('/professor/publications')

    assert resp.status_code == 200
    assert b'/professor/publications/sync' in resp.data


# =====================================================================
# Slice (c): pagination — a bookmark in the URL
#
# "Run the sync again later for the rest" used to re-fetch the same
# first 60 works. Now a truncated run offers a link carrying
# ?offset=60, and the next run starts from work 61. Each run states
# its window; "up to date" is reserved for a run that covered the
# whole record.
# =====================================================================

def test_offset_is_passed_to_the_fetcher(app, seeded_pubs, monkeypatch):
    import app.publication_sync as sync
    seen = {}

    def spy(orcid, years=0, offset=0):
        seen['offset'] = offset
        return {'works': [], 'total': 97, 'examined': 37, 'truncated': False}
    monkeypatch.setattr(sync, 'fetch_orcid_works', spy)
    from app.publication_sync import find_new_publications

    with app.app_context():
        result = find_new_publications(seeded_pubs, '0000-0000-0000-0000',
                                       offset=60)

    assert seen['offset'] == 60
    assert result['offset'] == 60
    assert result['next_offset'] == 97, 'offset + examined'


def test_truncated_page_links_to_the_next_window(app, logged_in_client,
                                                 seeded_pubs, monkeypatch):
    """The continue button must carry the bookmark: offset=60."""
    import app.publication_sync as sync
    monkeypatch.setattr(
        sync, 'fetch_orcid_works',
        lambda orcid, years=0, offset=0: {
            'works': [], 'total': 97, 'examined': 60, 'truncated': True})

    resp = logged_in_client.get('/professor/publications/sync')

    assert resp.status_code == 200
    assert b'offset=60' in resp.data, \
        'a truncated run must offer a link that resumes at the next work'


def test_offset_run_states_its_window(app, logged_in_client, seeded_pubs,
                                      monkeypatch):
    """A continued run says which works it covered — and does not claim
    the whole record is up to date."""
    import app.publication_sync as sync
    monkeypatch.setattr(
        sync, 'fetch_orcid_works',
        lambda orcid, years=0, offset=0: {
            'works': [], 'total': 97, 'examined': 37, 'truncated': False})

    resp = logged_in_client.get('/professor/publications/sync?offset=60')

    assert resp.status_code == 200
    assert b'61' in resp.data and b'97' in resp.data, \
        'the window (works 61-97) must be stated'
    assert b'up to date' not in resp.data.lower(), \
        'a windowed run must not claim the whole record is current'


def test_publications_page_links_to_sync(app, logged_in_client,
                                         seed_professor):
    resp = logged_in_client.get('/professor/publications')

    assert resp.status_code == 200
    assert b'/publications/sync' in resp.data, \
        'the sync page must be reachable from the publications page'
