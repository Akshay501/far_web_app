"""
bibtex_parser.py — Parse and write .bib files for the FAR web application.

Handles make_cv's scholarship.bib format including:
- Standard entry types: article, inproceedings, misc, book, incollection
- make_cv custom fields: citations, gsid, btacqueried, keywords (category)
- JabRef metadata comments (preserved on export)
- LaTeX special characters (stripped for display, preserved in RawBibtex)
"""

import re
import io
import bibtexparser
from bibtexparser.bparser import BibTexParser
from pylatexenc.latex2text import LatexNodes2Text


# ── Category mapping ────────────────────────────────────────────────────────
# Maps make_cv keyword values → human-readable display names
CATEGORY_MAP = {
    'journal':    'Journal Articles',
    'refereed':   'Refereed Conference Papers',
    'conference': 'Conference Presentations',
    'book':       'Books & Book Chapters',
    'patent':     'Patents',
    'invited':    'Invited Talks',
    'techreport': 'Technical Reports',
    'arxiv':      'arXiv Papers',
    'ignore':     'Ignored',
}

# Display order for tabs
CATEGORY_ORDER = [
    'journal', 'refereed', 'conference', 'book',
    'patent', 'invited', 'techreport', 'arxiv', 'ignore'
]


def _strip_markers(text):
    """Remove make_cv student markers \\gs \\us from display text."""
    if not text:
        return text
    import re
    return re.sub(r'\\(gs|us|un\{[^}]*\})', '', str(text)).strip()


def _strip_braces(text):
    """Remove LaTeX braces used for capitalization: {Smart Grids} → Smart Grids"""
    if not text:
        return text
    result = re.sub(r'\{([^{}]*)\}', r'\1', str(text))
    return result.strip()


_LATEX_DISPLAY = LatexNodes2Text()


def _latex_display(text):
    """
    LaTeX -> readable unicode, for DISPLAY fields only.

    Uses pylatexenc (the converter make_cv itself relies on) instead of
    bibtexparser's convert_to_unicode / latex_to_unicode, which match
    macros greedily by prefix: \\omega became '$ømega$' (\\o is the ø
    macro, 'mega' stranded), \\lambda became '$łambda$', and even
    ordinary accents could land on the wrong letter. Two of the 252
    production titles were corrupted this way — found when the ORCID
    sync offered an already-owned paper as "new".

    Never applied to url/doi/pages and similar: '%' starts a LaTeX
    comment and '~' is a non-breaking space, so decoding a URL destroys
    it. RawBibtex is never touched by any conversion.
    """
    if not text:
        return text
    try:
        return _LATEX_DISPLAY.latex_to_text(str(text)).strip()
    except Exception:
        return _strip_braces(str(text))


def _get_category(keywords_str):
    """
    Extract make_cv category from keywords field.
    keywords field may contain multiple values e.g. 'journal; gs_id=abc'
    Returns the first recognized category keyword.
    """
    if not keywords_str:
        return 'other'
    keywords = [k.strip().lower() for k in re.split(r'[;,]', keywords_str)]
    for kw in keywords:
        if kw in CATEGORY_MAP:
            return kw
    return 'other'


def _entry_to_raw_bibtex(entry):
    """Convert a bibtexparser entry dict back to raw BibTeX string."""
    entry_type = entry.get('ENTRYTYPE', 'misc')
    cite_key = entry.get('ID', 'unknown')

    # Fields to skip (internal bibtexparser fields)
    skip_fields = {'ENTRYTYPE', 'ID'}

    lines = [f'@{entry_type}{{{cite_key},']
    for key, value in entry.items():
        if key in skip_fields:
            continue
        # Wrap value in braces
        lines.append(f'  {key:<14} = {{{value}}},')
    lines.append('}')
    return '\n'.join(lines)


def parse_bib_file(filepath):
    """
    Parse a .bib file and return a list of publication dicts.

    Each dict contains:
        bibkey, type, title, authors, year, journal, booktitle,
        volume, issue, pages, doi, url, publisher, keywords,
        category, citations, abstract, raw_bibtex, extra_fields
    """
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            text = f.read()

        # ONE parse, NO customization — the faithful entries that become
        # RawBibtex. Display fields derive from these via _latex_display.
        # (A second parse with bibtexparser's convert_to_unicode used to
        # supply display fields; that converter corrupted titles — see
        # _latex_display's docstring and tests/test_bibtex_display.py.)
        raw_parser = BibTexParser(common_strings=True)
        raw_parser.ignore_nonstandard_types = False
        raw_db = bibtexparser.load(io.StringIO(text), parser=raw_parser)

        publications = []
        for raw_entry in raw_db.entries:
            raw = _entry_to_raw_bibtex(raw_entry)

            # Extract category from keywords
            keywords_raw = raw_entry.get('keywords', '')
            category = _get_category(keywords_raw)

            # Author display: strip \gs/\us markers FIRST, then decode.
            # The order is load-bearing: \us reads as a breve accent to any
            # LaTeX decoder and would corrupt the name into "s̆".
            raw_author = raw_entry.get('author', '')
            disp_author = _latex_display(_strip_markers(raw_author))

            # Build clean publication dict (display fields stripped of markers)
            pub = {
                'bibkey':       raw_entry.get('ID', ''),
                'type':         raw_entry.get('ENTRYTYPE', 'misc'),
                'title':        _latex_display(raw_entry.get('title', '')),
                'authors':      disp_author,
                'year':         _parse_year(raw_entry.get('year', '')),
                'journal':      _latex_display(raw_entry.get('journal', '') or raw_entry.get('journaltitle', '')),
                'booktitle':    _latex_display(raw_entry.get('booktitle', '') or raw_entry.get('address', '')),
                'volume':       raw_entry.get('volume', ''),
                'issue':        raw_entry.get('number', '') or raw_entry.get('issue', ''),
                'pages':        raw_entry.get('pages', '').replace('--', '–'),
                'doi':          raw_entry.get('doi', ''),
                'url':          raw_entry.get('url', ''),
                'publisher':    _latex_display(raw_entry.get('publisher', '')),
                'keywords':     keywords_raw,
                'category':     category,
                'citations':    _parse_int(raw_entry.get('citations', 0)),
                'abstract':     _latex_display(raw_entry.get('abstract', '')),
                'raw_bibtex':   raw,
                # Store any extra make_cv fields
                'extra_fields': {
                    k: v for k, v in raw_entry.items()
                    if k not in {
                        'ID', 'ENTRYTYPE', 'title', 'author', 'year',
                        'journal', 'journaltitle', 'booktitle', 'volume',
                        'number', 'issue', 'pages', 'doi', 'url',
                        'publisher', 'keywords', 'citations', 'abstract',
                        'address'
                    }
                }
            }
            publications.append(pub)

        return publications, None  # (list, error)

    except Exception as e:
        return [], str(e)


def _parse_year(val):
    """Safely parse year to int."""
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def _parse_int(val):
    """Safely parse integer field."""
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return 0


def entry_to_bibtex_string(pub_dict):
    """
    Convert a publication dict (from DB or form) back to BibTeX string.
    Used when exporting .bib file.
    """
    entry_type = pub_dict.get('type', 'misc')
    bibkey = pub_dict.get('bibkey', 'unknown')

    lines = [f'@{entry_type}{{{bibkey},']

    def add_field(name, value):
        if value:
            lines.append(f'  {name:<14} = {{{value}}},')

    add_field('author',    pub_dict.get('authors', ''))
    add_field('title',     pub_dict.get('title', ''))
    add_field('year',      pub_dict.get('year', ''))
    add_field('journal',   pub_dict.get('journal', ''))
    add_field('booktitle', pub_dict.get('booktitle', ''))
    add_field('volume',    pub_dict.get('volume', ''))
    add_field('number',    pub_dict.get('issue', ''))
    add_field('pages',     pub_dict.get('pages', '').replace('–', '--'))
    add_field('doi',       pub_dict.get('doi', ''))
    add_field('url',       pub_dict.get('url', ''))
    add_field('publisher', pub_dict.get('publisher', ''))
    add_field('keywords',  pub_dict.get('keywords', ''))
    add_field('abstract',  pub_dict.get('abstract', ''))
    if pub_dict.get('citations'):
        add_field('citations', str(pub_dict.get('citations', 0)))

    lines.append('}')
    return '\n'.join(lines)


def patch_raw_bibtex(raw_bibtex, updates, new_id=None, set_author=None):
    """
    Surgically update an existing RawBibtex entry WITHOUT going through
    convert_to_unicode, so make_cv markers (\\gs, \\us) and every extra
    BibDesk/JabRef field (month, address, editor, bdsk-*, etc.) are preserved.

    Parameters:
        raw_bibtex : the existing RawBibtex string for one entry
        updates    : {bibtex_field: value} to set. Empty/None value removes
                     the field. Use bibtex field names (e.g. 'number' not 'issue').
        new_id     : if given, replace the cite key (used by duplicate).
        set_author : if not None, overwrite the author field with this exact
                     string. Only pass this when the professor actually changed
                     the authors — otherwise the author line is left untouched
                     so markers survive.

    Returns the new RawBibtex string. On any parse failure, returns the
    original unchanged (safe fallback).
    """
    try:
        parser = BibTexParser(common_strings=True)
        parser.ignore_nonstandard_types = False
        db = bibtexparser.load(io.StringIO(raw_bibtex), parser=parser)
        if not db.entries:
            return raw_bibtex
        entry = db.entries[0]

        if new_id:
            entry['ID'] = new_id
        if set_author is not None:
            entry['author'] = set_author
        for field, value in updates.items():
            if value is None or value == '':
                entry.pop(field, None)
            else:
                entry[field] = str(value)

        return _entry_to_raw_bibtex(entry)
    except Exception:
        return raw_bibtex


def export_bib_file(publications, filepath, include_jabref_header=True):
    """
    Export a list of publication dicts to a .bib file.
    Preserves make_cv/JabRef compatibility.
    """
    jabref_header = """@comment{jabref-meta: grouping: 0 AllEntriesGroup:; 1 KeywordGroup:journal\\;0\\;keywords\\;journal\\;0\\;0\\;1\\;; 1 KeywordGroup:refereed\\;0\\;keywords\\;refereed\\;0\\;0\\;1\\;; 1 KeywordGroup:conference\\;0\\;keywords\\;conference\\;0\\;0\\;1\\;; 1 KeywordGroup:book\\;0\\;keywords\\;book\\;0\\;0\\;1\\;; 1 KeywordGroup:patent\\;0\\;keywords\\;patent\\;0\\;0\\;1\\;; 1 KeywordGroup:invited\\;0\\;keywords\\;invited\\;0\\;0\\;1\\;; 1 KeywordGroup:techreport\\;0\\;keywords\\;techreport\\;0\\;0\\;1\\;; }

"""

    with open(filepath, 'w', encoding='utf-8') as f:
        if include_jabref_header:
            f.write(jabref_header)

        for pub in publications:
            # Use raw_bibtex if available (preserves all original fields)
            # Otherwise reconstruct from parsed fields
            if pub.get('raw_bibtex'):
                f.write(pub['raw_bibtex'])
            else:
                f.write(entry_to_bibtex_string(pub))
            f.write('\n\n')


def group_by_category(publications):
    """
    Group publications by category for tab display.
    Returns OrderedDict in display order.
    """
    groups = {cat: [] for cat in CATEGORY_ORDER}
    groups['other'] = []

    for pub in publications:
        cat = pub.get('category', 'other')
        if cat in groups:
            groups[cat].append(pub)
        else:
            groups['other'].append(pub)

    # Sort each group by year descending — handle str/int mixed types safely
    for cat in groups:
        groups[cat].sort(key=lambda p: int(p.get('year') or 0) if p.get('year') else 0, reverse=True)

    return groups


def get_category_label(category_key):
    """Get human-readable label for a category key."""
    return CATEGORY_MAP.get(category_key, 'Other Publications')


