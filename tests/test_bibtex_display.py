"""
Tests for the bib import's DISPLAY-field conversion (the ømega bug).

The importer stores two versions of every publication: RawBibtex (the
faithful original — generates every FAR and CV) and display fields
(Title, Authors, Journal... shown in the browser and used by the ORCID
sync's dedup). The display conversion used bibtexparser's
convert_to_unicode / latex_to_unicode, which match LaTeX macros
greedily by prefix:

    $\\omega$   ->  $ømega$      (\\o is the ø macro; 'mega' stranded)
    $\\lambda$  ->  $łambda$     (\\l is ł)
    Fl\\"ow     ->  Fl\\ẅ        (accent lands on the wrong letter)

Two of Brian's 252 titles were corrupted this way in the real database
— found because the ORCID sync offered a paper as "new" that the DB
already had, under a title the corruption made unrecognizable.

The fix: every display field goes through pylatexenc's LatexNodes2Text
(the converter make_cv itself uses), applied to human-text fields only
— never url/doi, where '%' would start a LaTeX comment and truncate the
value. RawBibtex remains untouched by ANY conversion, and markers are
stripped BEFORE conversion (\\us reads as a breve accent otherwise).
"""
import pytest

from app.bibtex_parser import parse_bib_file


def _parse_one(tmp_path, fields):
    body = '\n'.join(f'  {k} = {{{v}}},' for k, v in fields.items())
    bib = f'@article{{testkey2020,\n{body}\n}}\n'
    p = tmp_path / 'one.bib'
    p.write_text(bib, encoding='utf-8')
    pubs, err = parse_bib_file(str(p))
    assert err is None, f'parse failed: {err}'
    assert len(pubs) == 1
    return pubs[0]


# ------------------------------------------------ titles decode correctly

@pytest.mark.parametrize('raw_title,must_have,must_not_have', [
    (r'Modified k-$\omega$ Turbulence Model', 'ω', ['ømega', '$', '\\']),
    (r'A Study of $\lambda$-Type Instabilities', 'λ', ['łambda', '$']),
    (r'Effect on Fl\"ow Structures', 'Flöw', ['\\']),
    (r"Work of Jos\'e Garcia", 'José', ['\\']),
    (r'{H}igh-{O}rder Methods for {CFD}', 'High-Order', ['{', '}']),
])
def test_title_decodes_to_readable_unicode(tmp_path, raw_title,
                                           must_have, must_not_have):
    pub = _parse_one(tmp_path, {'title': raw_title, 'year': '2020'})

    assert must_have in pub['title'], pub['title']
    for bad in must_not_have:
        assert bad not in pub['title'], \
            f'{bad!r} must not survive in the display title: {pub["title"]!r}'


def test_journal_decodes_too(tmp_path):
    pub = _parse_one(tmp_path, {
        'title': 'T', 'year': '2020',
        'journal': r'Zeitschrift f\"ur Flugwissenschaften'})

    assert 'für' in pub['journal'], pub['journal']
    assert '\\' not in pub['journal']


# ------------------------------- markers: display clean, RawBibtex intact

def test_markers_stripped_from_display_but_kept_in_raw(tmp_path):
    """THE invariant. Display never shows \\gs/\\us (and \\us must not
    become a breve-accented s̆); RawBibtex keeps both verbatim, because
    that is what generates the documents and drives the marker editor."""
    pub = _parse_one(tmp_path, {
        'title': 'Marker Test', 'year': '2020',
        'author': r'Helenbrook, B. and \gs Doe, Jane and \us Roe, Richard'})

    disp = pub['authors']
    assert 'Doe' in disp and 'Roe' in disp
    assert '\\gs' not in disp and '\\us' not in disp
    assert '\u0306' not in disp and 's̆' not in disp, \
        'the \\us marker must never be read as a breve accent'

    raw = pub['raw_bibtex']
    assert r'\gs' in raw and r'\us' in raw, \
        'RawBibtex must keep the markers verbatim'


def test_accented_author_decodes(tmp_path):
    pub = _parse_one(tmp_path, {
        'title': 'T', 'year': '2020',
        'author': r"Garc\'ia, Jos\'e and M\"uller, K."})

    assert 'García' in pub['authors']
    assert 'Müller' in pub['authors']
    assert '\\' not in pub['authors']


# ------------------------------------ fields that must NEVER be converted

def test_url_and_doi_pass_through_verbatim(tmp_path):
    """'%' starts a LaTeX comment and '~' is a non-breaking space — a
    LaTeX decoder applied to a URL destroys it. These fields bypass
    conversion entirely."""
    url = 'http://example.com/~user/paper%20final_v2.pdf'
    doi = '10.1115/AJKFluids2019-5501'
    pub = _parse_one(tmp_path, {
        'title': 'T', 'year': '2020', 'url': url, 'doi': doi})

    assert pub['url'] == url
    assert pub['doi'] == doi


def test_category_extraction_still_works(tmp_path):
    pub = _parse_one(tmp_path, {
        'title': 'T', 'year': '2020', 'keywords': 'journal'})

    assert pub['category'] == 'journal'
