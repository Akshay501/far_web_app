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
import os
import re
import tempfile
import time

from flask import current_app
from pylatexenc.latex2text import LatexNodes2Text

from app.bibtex_parser import parse_bib_file
from app.utils import execute_query

# Bounds for one sync run.
MAX_WORKS = 60
TIME_BUDGET_SECONDS = 45

# ORCID work types -> the category badge shown on the review screen.
# Display-level for slice (a); slice (b) maps onto the app's publication
# categories at insert time.
# ORCID work types -> make_cv keyword vocabulary (the same categories the
# publications page uses). These are GUESSES the professor confirms via a
# dropdown on the review screen — the human check that replaces make_cv's
# silent auto-classification.
_CATEGORY_BY_ORCID_TYPE = {
    'journal-article': 'journal',
    'conference-paper': 'refereed',
    'conference-abstract': 'conference',
    'book': 'book',
    'book-chapter': 'book',
    'preprint': 'arxiv',
    'patent': 'patent',
    'report': 'techreport',
}


_LATEX_TEXT = LatexNodes2Text()


def _title_key(title, year):
    """
    Normalized title+year — make_cv's make_title_id recipe, verbatim:
    decode LaTeX to text FIRST, then lowercase, strip non-alphanumerics,
    append the year. The decode step is load-bearing: a database title
    holding "$\\omega$" and an ORCID title holding "ω" must produce the
    same key. The first live run proved it — a real paper was offered
    as "new" because the two forms didn't match.
    """
    try:
        text = _LATEX_TEXT.latex_to_text(str(title or ''))
    except Exception:
        text = str(title or '')
    t = re.sub(r'[^a-z0-9]+', '', text.lower())
    return f"{t}{year or ''}"


def _guess_category(orcid_type):
    return _CATEGORY_BY_ORCID_TYPE.get((orcid_type or '').lower(), 'journal')


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
    total = len(groups)
    examined = 0
    hit_budget = False
    if total > MAX_WORKS:
        current_app.logger.info(
            'ORCID record has %s works; fetching the first %s',
            total, MAX_WORKS)

    for group in groups[:MAX_WORKS]:
        if time.monotonic() > deadline:
            current_app.logger.warning(
                'ORCID fetch hit the %ss budget after %s works',
                TIME_BUDGET_SECONDS, examined)
            hit_budget = True
            break
        examined += 1

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
    return {
        'works': out,
        'total': total,
        'examined': examined,
        'truncated': hit_budget or total > MAX_WORKS,
    }


def _report(candidates=None, total=None, examined=0, truncated=False,
            error=None):
    return {'candidates': candidates or [], 'total_works': total,
            'examined': examined, 'truncated': truncated, 'error': error}


def find_new_publications(professor_key, orcid_id, years=0):
    """
    Fetch -> dedup against PUBLICATIONS -> report.

    Returns a REPORT, not just a list, so the page can tell the truth:

        {'candidates': [...],      new works not in the database
         'total_works': int|None,  how many works the ORCID record holds
         'examined': int,          how many we fetched details for
         'truncated': bool,        stopped at the cap / time budget
         'error': None|str}        human-readable failure, if any

    The distinction matters most when candidates is empty: "checked all
    42, nothing new" and "the fetch crashed, checked nothing" must never
    look the same. A sync problem is reported, never raised — and never
    dressed as success.
    """
    if not (orcid_id or '').strip():
        return _report()

    try:
        fetched = fetch_orcid_works(orcid_id, years=years)
    except Exception as exc:
        current_app.logger.warning(
            'ORCID fetch failed for professor %s: %s', professor_key, exc)
        return _report(error='Could not reach ORCID. Nothing was checked '
                             '— please try again in a moment.')

    rows = execute_query(
        'SELECT Title, Year, DOI FROM PUBLICATIONS WHERE ProfessorKey = %s',
        (professor_key,)) or []
    known_dois = {(r.get('DOI') or '').strip().lower()
                  for r in rows if (r.get('DOI') or '').strip()}
    known_titles = {_title_key(r.get('Title'), r.get('Year')) for r in rows}

    candidates = []
    for work in fetched['works']:
        doi = (work.get('doi') or '').strip().lower()
        if doi and doi in known_dois:
            continue
        if _title_key(work.get('title'), work.get('year')) in known_titles:
            continue
        candidates.append(work)

    current_app.logger.info(
        'ORCID sync for professor %s: %s of %s works examined, %s new%s',
        professor_key, fetched['examined'], fetched['total'],
        len(candidates), ' (truncated)' if fetched['truncated'] else '')
    return _report(candidates, total=fetched['total'],
                   examined=fetched['examined'],
                   truncated=fetched['truncated'])


def _inject_keyword(raw_bibtex, category):
    """
    Ensure the stored entry carries the chosen category as a bibtex
    keywords field. This is what makes the review screen's choice REAL:
    scholarship.bib is rebuilt from RawBibtex on every generation, and
    make_cv sections publications by the keywords field in the bib — an
    entry without one gets re-guessed by make_cv's missing-type step,
    ignoring whatever the professor picked.
    """
    if not category:
        return raw_bibtex
    # Replace an existing keywords field, if any (the chosen category wins).
    replaced, n = re.subn(r'(?im)^(\s*keywords\s*=\s*)\{[^}]*\}',
                          lambda m: m.group(1) + '{' + category + '}',
                          raw_bibtex)
    if n:
        return replaced
    # Otherwise insert one before the closing brace.
    idx = raw_bibtex.rfind('}')
    if idx == -1:
        return raw_bibtex
    return (raw_bibtex[:idx].rstrip().rstrip(',')
            + f',\n  keywords       = {{{category}}},\n}}')


def import_candidates(professor_key, candidates):
    """
    Slice (b): write accepted candidates into PUBLICATIONS.

    Safety rules, in order:
      1. Dedup runs AGAIN here, against the database as it is NOW — the
         review page's list may be stale (a paper added by hand while
         the tab sat open must not become a duplicate). Skips are
         counted and reported, never silent.
      2. Each candidate's raw_bibtex is parsed through the app's own
         fixed parser, so the display fields obey the same invariant as
         a bib upload: RawBibtex keeps markers and LaTeX verbatim,
         Title/Authors come out decoded.
      3. The professor_key comes from the session, never the form.

    Returns {'imported': n, 'skipped': n, 'failed': n}.
    """
    rows = execute_query(
        'SELECT Title, Year, DOI FROM PUBLICATIONS WHERE ProfessorKey = %s',
        (professor_key,)) or []
    known_dois = {(r.get('DOI') or '').strip().lower()
                  for r in rows if (r.get('DOI') or '').strip()}
    known_titles = {_title_key(r.get('Title'), r.get('Year')) for r in rows}

    imported = skipped = failed = 0
    for cand in candidates:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                    'w', suffix='.bib', delete=False,
                    encoding='utf-8') as tmp:
                tmp.write(cand.get('raw_bibtex') or '')
                tmp_path = tmp.name
            pubs, err = parse_bib_file(tmp_path)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if err or not pubs:
            failed += 1
            current_app.logger.warning(
                'Sync import: could not parse a candidate for professor '
                '%s: %s', professor_key, err)
            continue
        p = pubs[0]

        # Dedup on the PARSED values — the entry's own title/year/DOI,
        # not anything the browser claimed. Runs here, against the
        # database as it is NOW, so a stale review tab cannot create a
        # duplicate.
        doi = (p.get('doi') or '').strip().lower()
        tkey = _title_key(p.get('title'), p.get('year'))
        if (doi and doi in known_dois) or tkey in known_titles:
            skipped += 1
            continue

        raw_stored = _inject_keyword(p.get('raw_bibtex', ''),
                                     cand.get('category'))

        execute_query("""
            INSERT INTO PUBLICATIONS
                (ProfessorKey, BibKey, Type, Title, Authors, Year,
                 Journal, Booktitle, Volume, Issue, Pages, DOI, URL,
                 Publisher, Keywords, Citations, Abstract, RawBibtex)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            professor_key, p.get('bibkey', ''), p.get('type', 'misc'),
            p.get('title', ''), p.get('authors', ''), p.get('year'),
            p.get('journal', ''), p.get('booktitle', ''),
            p.get('volume', ''), p.get('issue', ''), p.get('pages', ''),
            p.get('doi', ''),
            p.get('url', ''), p.get('publisher', ''),
            cand.get('category') or p.get('category') or 'journal',
            p.get('citations', 0), p.get('abstract', ''),
            raw_stored,
        ), commit=True)
        imported += 1
        known_titles.add(tkey)
        if doi:
            known_dois.add(doi)

    current_app.logger.info(
        'Sync import for professor %s: %s imported, %s skipped, %s failed',
        professor_key, imported, skipped, failed)
    return {'imported': imported, 'skipped': skipped, 'failed': failed}
