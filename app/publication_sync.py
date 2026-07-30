"""
Publication sync (Issue #9). Slice (a): fetch from ORCID, dedup against
the database, return staged candidates for a review screen.

Why this module calls make_cv's small helpers rather than its top-level
bib_get_entries_orcid():

  1. For each new entry it asks "Is this btac entry correct... Y/N?"
     via input(). The prompt is skipped when make_cv's
     global_prefs.quiet is True — but flipping that flag means
     mutating module-global state shared by every request in the
     server process, and quiet mode then auto-accepts every
     autocompleted entry with no review, which is precisely the
     silent mutation of a professor's record that this feature's
     review screen exists to prevent.
  2. It runs BibtexAutocomplete on each new entry — third-party
     lookup calls whose timeouts we don't control — on top of the
     ORCID requests.
  3. It writes a .bib file, but this app's source of truth is the
     database: scholarship.bib is rebuilt from PUBLICATIONS.RawBibtex
     on every generation (write_bib_from_db), so anything written to a
     bib file here would be discarded on the next run. We want
     candidates in memory for a review screen, not a file.

  (Note for future readers: the rebinding of bib_database inside that
  function's loop LOOKS like it discards the existing bibliography, but
  it does not — the parser is created with expect_multiple_parse=True,
  which makes it accumulate, so each loads() returns the full library.
  Verified experimentally 2026-07-29 after the maintainer pointed it
  out.)

  The helpers underneath (get_all_works, get_work, extract_doi,
  extract_publication_year, bibtex_entry) are importable,
  side-effect-free, and carry timeout=10 on every request.

The stats-hang law applies throughout: per-request timeouts come from
the helpers; this module adds an overall time budget and a work cap
(get_work is one HTTP request PER publication, so a prolific record
would otherwise mean hundreds of sequential requests inside one web
request); failures degrade to "no candidates", never exceptions; and
sync is only ever an explicit user action, never part of generation.

Dedup keys, checked in order:
  - DOI, exact and case-insensitive — the strong key
  - title+year, normalized the same way make_cv's make_title_id does
    (lowercase alphanumerics + year), so punctuation and spacing
    differences don't defeat the match
"""
import re
import time

from flask import current_app

from app.utils import execute_query

# Bounds for one sync run.
MAX_WORKS = 60
TIME_BUDGET_SECONDS = 45

# ORCID work types -> the category badge shown on the review screen.
# Display-level for slice (a); slice (b) maps onto the app's publication
# categories at insert time.
_CATEGORY_BY_ORCID_TYPE = {
    'journal-article': 'journal',
    'conference-paper': 'conference',
    'conference-abstract': 'conference',
    'book': 'book',
    'book-chapter': 'book chapter',
    'preprint': 'preprint',
    'patent': 'patent',
    'dissertation-thesis': 'thesis',
    'report': 'report',
}


def _title_key(title, year):
    """Normalized title+year, mirroring make_cv's make_title_id:
    lowercase alphanumerics of the title with the year appended."""
    t = re.sub(r'[^a-z0-9]', '', (title or '').lower())
    return f"{t}{year or ''}"


def _guess_category(orcid_type):
    return _CATEGORY_BY_ORCID_TYPE.get((orcid_type or '').lower(), 'other')


def fetch_orcid_works(orcid_id, years=0):
    """
    Fetch a professor's works from ORCID's public API, one summary call
    plus one detail call per work, bounded by MAX_WORKS and
    TIME_BUDGET_SECONDS.

    Returns a list of dicts: title, year, doi, raw_bibtex, category.
    make_cv is imported lazily so the app (and the hermetic tests,
    which monkeypatch this function) never need it unless a real fetch
    happens.
    """
    from make_cv.bib_get_entries_orcid import (
        get_all_works, get_work, extract_doi, extract_publication_year,
        bibtex_entry, safe_value)

    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    out = []
    groups = get_all_works(orcid_id) or []
    if len(groups) > MAX_WORKS:
        current_app.logger.info(
            'ORCID record has %s works; fetching the first %s',
            len(groups), MAX_WORKS)

    for group in groups[:MAX_WORKS]:
        if time.monotonic() > deadline:
            current_app.logger.warning(
                'ORCID fetch hit the %ss budget after %s works',
                TIME_BUDGET_SECONDS, len(out))
            break

        summaries = group.get('work-summary') or []
        if not summaries:
            continue
        put_code = summaries[0].get('put-code')
        if put_code is None:
            continue

        work = get_work(orcid_id, put_code)
        if not work:
            continue

        year = extract_publication_year(work)
        if years:
            try:
                from datetime import date
                if year and int(year) < date.today().year - years:
                    continue
            except (TypeError, ValueError):
                pass

        title = safe_value(work, 'title', 'title', 'value') or ''
        if not title:
            continue

        out.append({
            'title': title,
            'year': str(year or ''),
            'doi': extract_doi(work),
            'raw_bibtex': bibtex_entry(work) or '',
            'category': _guess_category(work.get('type')),
        })
    return out


def find_new_publications(professor_key, orcid_id, years=0):
    """
    The slice (a) service: fetch -> dedup against PUBLICATIONS ->
    return candidates not yet in the database. Returns [] for a blank
    ORCID iD (without fetching) and [] on any fetch failure — a sync
    problem must never become a 500.
    """
    if not (orcid_id or '').strip():
        return []

    try:
        fetched = fetch_orcid_works(orcid_id, years=years)
    except Exception as exc:
        current_app.logger.warning(
            'ORCID fetch failed for professor %s: %s', professor_key, exc)
        return []

    rows = execute_query(
        'SELECT Title, Year, DOI FROM PUBLICATIONS WHERE ProfessorKey = %s',
        (professor_key,)) or []
    known_dois = {(r.get('DOI') or '').strip().lower()
                  for r in rows if (r.get('DOI') or '').strip()}
    known_titles = {_title_key(r.get('Title'), r.get('Year')) for r in rows}

    candidates = []
    for work in fetched:
        doi = (work.get('doi') or '').strip().lower()
        if doi and doi in known_dois:
            continue
        if _title_key(work.get('title'), work.get('year')) in known_titles:
            continue
        candidates.append(work)

    current_app.logger.info(
        'ORCID sync for professor %s: %s fetched, %s new',
        professor_key, len(fetched), len(candidates))
    return candidates
