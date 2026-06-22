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
from bibtexparser.customization import convert_to_unicode
from bibtexparser.latexenc import latex_to_unicode


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

        # Parse 1 — with unicode conversion. Used for the DISPLAY fields
        # shown in the browser (accents become real unicode characters).
        disp_parser = BibTexParser(common_strings=True)
        disp_parser.customization = convert_to_unicode
        disp_parser.ignore_nonstandard_types = False
        disp_db = bibtexparser.load(io.StringIO(text), parser=disp_parser)

        # Parse 2 — NO customization. Used to build the faithful RawBibtex
        # stored in the DB. This is essential: convert_to_unicode treats the
        # make_cv undergraduate marker \us as a LaTeX breve accent and corrupts
        # it into "s̆". Parsing without customization keeps \gs and \us intact.
        raw_parser = BibTexParser(common_strings=True)
        raw_parser.ignore_nonstandard_types = False
        raw_db = bibtexparser.load(io.StringIO(text), parser=raw_parser)
        raw_by_id = {e.get('ID', ''): e for e in raw_db.entries}

        publications = []
        for entry in disp_db.entries:
            ekey = entry.get('ID', '')
            # Faithful raw entry (markers preserved); fall back to display entry
            raw_entry = raw_by_id.get(ekey, entry)
            raw = _entry_to_raw_bibtex(raw_entry)

            # Extract category from keywords
            keywords_raw = entry.get('keywords', '')
            category = _get_category(keywords_raw)

            # Author display: take the FAITHFUL raw author (markers intact),
            # strip \gs/\us first, THEN convert accents. Doing it in this order
            # avoids \us being mis-read as a breve accent (which would leave a
            # stray "s̆" in the displayed name).
            raw_author = raw_entry.get('author', '') or entry.get('author', '')
            disp_author = _strip_braces(latex_to_unicode(_strip_markers(raw_author)))

            # Build clean publication dict (display fields stripped of markers)
            pub = {
                'bibkey':       entry.get('ID', ''),
                'type':         entry.get('ENTRYTYPE', 'misc'),
                'title':        _strip_braces(entry.get('title', '')),
                'authors':      disp_author,
                'year':         _parse_year(entry.get('year', '')),
                'journal':      _strip_braces(entry.get('journal', '') or entry.get('journaltitle', '')),
                'booktitle':    _strip_braces(entry.get('booktitle', '') or entry.get('address', '')),
                'volume':       entry.get('volume', ''),
                'issue':        entry.get('number', '') or entry.get('issue', ''),
                'pages':        entry.get('pages', '').replace('--', '–'),
                'doi':          entry.get('doi', ''),
                'url':          entry.get('url', ''),
                'publisher':    _strip_braces(entry.get('publisher', '')),
                'keywords':     keywords_raw,
                'category':     category,
                'citations':    _parse_int(entry.get('citations', 0)),
                'abstract':     _strip_braces(entry.get('abstract', '')),
                'raw_bibtex':   raw,
                # Store any extra make_cv fields
                'extra_fields': {
                    k: v for k, v in entry.items()
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


