"""
Scopus as the second sync source. The review template and the import
route are reused untouched (source-agnostic raw+category contract), so
these tests cover what is NEW: the fetch, its safety rails, the
candidate mapping, and the dedup/pagination report.

make_cv's own Scopus fetcher can never run server-side — it has an
input() prompt and pybliometrics prompts interactively on first run.
The app calls the REST API directly. Hermetic: requests is faked.
"""
import json

import bibtexparser
import pytest

import app.publication_sync as ps


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def _payload(entries, total):
    return {'search-results': {
        'opensearch:totalResults': str(total), 'entry': entries}}


ENTRY = {'dc:title': 'Adaptive Mesh {Refinement} for Flows',
         'prism:coverDate': '2026-03-01', 'prism:doi': '10.1/abc',
         'prism:publicationName': 'J. Comp. Physics',
         'dc:creator': 'Helenbrook B.', 'subtypeDescription': 'Article'}
CONF = {'dc:title': 'A Conference Thing', 'prism:coverDate': '2025-07-01',
        'subtypeDescription': 'Conference Paper'}


def test_fetch_carries_hard_timeout_and_scoped_query(app, monkeypatch):
    """STATS-HANG LAW: the request must carry a hard timeout, and the
    query must be scoped to the professor's AU-ID."""
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, timeout=timeout)
        return FakeResp(200, _payload([], 0))
    monkeypatch.setattr('requests.get', fake_get)

    ps._scopus_fetch_page('7004212771', 'k-123', start=0)
    assert seen['timeout'] == ps.SCOPUS_TIMEOUT and seen['timeout'] is not None
    assert 'AU-ID(7004212771)' in seen['params']['query']
    assert seen['params']['apiKey'] == 'k-123'


def test_auth_failure_is_honest_and_skips_the_db(app, monkeypatch):
    """401/403 must produce an error report mentioning the campus-IP
    limitation of personal keys — and must never look like 'up to
    date'. The DB is never touched: execute_query would blow up."""
    monkeypatch.setattr('requests.get',
                        lambda *a, **k: FakeResp(401))
    monkeypatch.setattr(ps, 'execute_query',
                        lambda *a, **k: pytest.fail('DB touched on auth error'))
    with app.app_context():
        report = ps.find_new_scopus_publications(1, '7004', 'bad-key')
    assert report['candidates'] == []
    assert 'campus' in report['error']
    assert report['total_works'] is None, 'must not claim a checked total'


def test_timeout_is_reported_not_raised(app, monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.exceptions.Timeout()
    monkeypatch.setattr('requests.get', boom)
    with app.app_context():
        report = ps.find_new_scopus_publications(1, '7004', 'k')
    assert 'did not respond' in report['error']


def test_missing_key_never_calls_scopus(app, monkeypatch):
    monkeypatch.setattr('requests.get',
                        lambda *a, **k: pytest.fail('HTTP call without a key'))
    with app.app_context():
        report = ps.find_new_scopus_publications(1, '7004', None)
    assert 'FAR_SCOPUS_API_KEY' in report['error']


def test_candidate_maps_and_raw_bibtex_parses(app):
    cand = ps._scopus_entry_to_candidate(ENTRY)
    assert cand['title'].startswith('Adaptive Mesh')
    assert cand['year'] == '2026' and cand['doi'] == '10.1/abc'
    assert cand['category'] == 'journal'
    parsed = bibtexparser.loads(cand['raw_bibtex'])
    assert len(parsed.entries) == 1, 'raw bibtex must be parseable'
    e = parsed.entries[0]
    assert e['year'] == '2026' and e['doi'] == '10.1/abc'
    assert 'Refinement' in e['title']

    conf = ps._scopus_entry_to_candidate(CONF)
    assert conf['category'] == 'conference'
    assert '@inproceedings' in conf['raw_bibtex']


def test_dedup_and_truncation_report(app, monkeypatch):
    """3 fetched, 1 already in the DB -> 2 candidates; 60 total from
    offset 0 -> truncated, next_offset = examined."""
    third = dict(ENTRY, **{'dc:title': 'A Brand New Third Paper',
                           'prism:coverDate': '2024-01-01'})
    monkeypatch.setattr('requests.get', lambda *a, **k: FakeResp(
        200, _payload([ENTRY, CONF, third], 60)))
    monkeypatch.setattr(ps, 'execute_query', lambda *a, **k: [
        {'Title': 'Adaptive Mesh Refinement for Flows', 'Year': '2026'}])
    with app.app_context():
        report = ps.find_new_scopus_publications(1, '7004', 'k', offset=0)
    assert len(report['candidates']) == 2
    assert report['examined'] == 3 and report['total_works'] == 60
    assert report['truncated'] is True and report['next_offset'] == 3


def test_continue_link_stays_on_the_same_source(app, monkeypatch,
                                                logged_in_client):
    """A 'check the next works' click on the SCOPUS page must page
    through SCOPUS. The shared template originally hardcoded the ORCID
    endpoint, so paging silently switched source mid-review — caught
    live 2026-08-18 (log showed /sync?offset=25 after /sync/scopus)."""
    monkeypatch.setattr('requests.get', lambda *a, **k: FakeResp(
        200, _payload([ENTRY], 60)))
    monkeypatch.setattr(
        'app.routes.professor.execute_query',
        lambda q, *a, **k: ({'ScopusID': '6602791670'}
                            if 'ScopusID' in q else []))
    resp = logged_in_client.get('/professor/publications/sync/scopus')
    html = resp.data.decode()
    assert 'sync/scopus?offset=' in html, \
        'the continue link must stay on the Scopus source'
    assert 'publications/sync?offset=' not in html, \
        'it must not jump to the ORCID endpoint'
