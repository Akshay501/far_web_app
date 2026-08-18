"""
Professor folder creation service.

Creates a professor's on-disk folder from the server-side scaffold template
(a local clone of the make_cv_files repo), then patches the personal files:

  - personal_data.txt   -> the professor's publication-source IDs
  - ContactInfo.tex     -> name, \\mynames, email, institution (from config)
  - every make_cv.cfg   -> stats fetch disabled (creation-time known-good
                           default: the upstream stats fetch has no timeout
                           and hangs generation; revisit when make_cv
                           ships a fix)

Design properties:
  - No database access. Identity arrives as parameters, so the service is
    pure filesystem work and testable without MySQL.
  - Idempotent. An existing folder is NEVER touched ('exists') — calling
    this twice can never destroy a professor's data.
  - Cleans up after itself. On any failure the partial copy is removed and
    FolderCreationError is raised; the caller decides how loudly to react.
"""
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

from flask import current_app


class FolderCreationError(Exception):
    """A professor folder could not be created. Any partial copy has
    already been cleaned up before this is raised."""


def folder_name_for(professor_key, prof=None):
    """
    On-disk folder name for a professor — the single source of truth,
    shared by path resolution (generate.get_professor_folder) and folder
    creation here. Currently the bare ProfessorKey (e.g. "9001"). If a
    human-readable hybrid is ever wanted ("9001_smith-jane"), this is the
    only function that changes.
    """
    return str(professor_key)


# ---------------------------------------------------------------------------
# LaTeX handling
# ---------------------------------------------------------------------------

_LATEX_SPECIALS = {
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
}


def _latex_escape(text):
    """Escape LaTeX special characters in human-entered text (names,
    addresses). Processed character-by-character so introduced backslashes
    are never re-escaped. Unicode (e.g. accented letters) passes through —
    the pipeline is XeLaTeX, which is Unicode-native."""
    if text is None:
        return ''
    out = []
    for ch in str(text):
        if ch == '\\':
            out.append(r'\textbackslash{}')
        else:
            out.append(_LATEX_SPECIALS.get(ch, ch))
    return ''.join(out)


# Generated from our own template (using the same commands the scaffold's
# ContactInfo.tex uses) rather than regex-editing the scaffold file —
# deterministic output beats pattern-matching on a file upstream may reword.
# usePhoto starts false: the template ships a placeholder photo, and a new
# professor's report should not display it; they can enable it after
# uploading a real photo.
# Written into every ContactInfo.tex the app generates, so a later run can
# tell "we wrote this" from "a human wrote this". Hand-authored files often
# carry a phone number, LinkedIn and webpage that the database has no column
# for — refreshing those would silently destroy real contact details.
CONTACTINFO_MARKER = '% Generated from the FAR web app database'

_CONTACTINFO_TEMPLATE = (
    "% Generated from the FAR web app database. Edits here are replaced on\n"
    "% each generation - change your details in your profile instead.\n"
    "% Specify your last name/first initial to have it be bold in the author list\n"
    "% Multiple names can be listed separated by commas, e.g. {{Lastname/F,Other/A}}\n"
    "\\mynames{{{mynames}}}\n"
    "\n"
    "%% Photo is only shown if \"usePhoto\" is true\n"
    "\\setboolean{{usePhoto}}{{false}}\n"
    "\n"
    "\\leftheader{{%\n"
    "  {{\\LARGE\\bfseries\\sffamily {display_name}}}\\\\\n"
    " {institution_line}\\\\\n"
    "  \\makefield{{\\faEnvelope[regular]}}{{\\href{{mailto:{email_url}}}{{{email_display}}}}}\n"
    "}}\n"
    "\n"
    "\\rightheader{{~}}\n"
    "\\ifthenelse{{\\boolean{{usePhoto}}}}{{\n"
    "\\photo[r]{{../PersonalData/photo}}\n"
    "\\photoscale{{0.13}}\n"
    "}}{{}}%\n"
)


def contactinfo_is_app_owned(path, template=None):
    """
    May the app rewrite this ContactInfo.tex?

    True when the file is missing, still byte-identical to the scaffold
    template (nobody has touched it), or carries our marker (we wrote
    it, so it is ours to keep current).

    False when a human authored it. Those files typically hold a phone
    number, LinkedIn and webpage that the database cannot supply, so
    overwriting would lose real data — and it would contradict the rule
    that PersonalData belongs to the professor.
    """
    if not os.path.isfile(path):
        return True
    try:
        current = open(path, encoding='utf-8').read()
    except OSError:
        return True

    if CONTACTINFO_MARKER in current:
        return True

    template = template or current_app.config.get('SCAFFOLD_TEMPLATE')
    if template:
        pristine = os.path.join(template, 'make_cv', 'PersonalData',
                                'ContactInfo.tex')
        try:
            if open(pristine, encoding='utf-8').read() == current:
                return True
        except OSError:
            pass
    return False


def render_contactinfo(path, first_name, last_name, email):
    """Write ContactInfo.tex for this professor: \\mynames for biblatex
    bolding, display name, institution details from config, and email."""
    institution = current_app.config.get('INSTITUTION', {}) or {}
    inst_name = _latex_escape(institution.get('name', ''))
    inst_addr = _latex_escape(institution.get('address', ''))
    institution_line = ', '.join(p for p in (inst_name, inst_addr) if p)

    first = (first_name or '').strip()
    last = (last_name or '').strip()
    initial = _latex_escape(first[0]) if first else ''
    mynames = f"{_latex_escape(last)}/{initial}"
    display_name = _latex_escape(f"{first} {last}".strip())

    text = _CONTACTINFO_TEMPLATE.format(
        mynames=mynames,
        display_name=display_name,
        institution_line=institution_line,
        email_url=email or '',          # raw for the mailto: URL
        email_display=_latex_escape(email or ''),
    )
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


# ---------------------------------------------------------------------------
# personal_data.txt and make_cv.cfg patching
# ---------------------------------------------------------------------------

def write_personal_data(path, google_id, orcid, scopus_id):
    """Write the publication-source IDs in the format make_cv reads
    (load_personal_data). Missing IDs are left blank, matching the
    scaffold's template file."""
    lines = [
        '# Personal data (IDs) for make_cv',
        f"googleid = {google_id or ''}",
        'webscraperid = ',
        f"scopusid = {scopus_id or ''}",
        f"orcid = {orcid or ''}",
    ]
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


_STATS_KEYS = ('scopusstats', 'googlestats')


def disable_stats_flags(folder):
    """Set scopusstats/googlestats to false in every make_cv.cfg under the
    folder. Creation-time default — see module docstring. Only these two
    keys are touched; all other lines pass through unchanged."""
    for dirpath, _dirnames, filenames in os.walk(folder):
        if 'make_cv.cfg' not in filenames:
            continue
        cfg_path = os.path.join(dirpath, 'make_cv.cfg')
        with open(cfg_path, encoding='utf-8') as f:
            text = f.read()
        for key in _STATS_KEYS:
            text = re.sub(rf'^{key}\s*=\s*true\s*$', f'{key} = false',
                          text, flags=re.MULTILINE)
        with open(cfg_path, 'w', encoding='utf-8') as f:
            f.write(text)


# ---------------------------------------------------------------------------
# Scaffold version stamp
# ---------------------------------------------------------------------------

# App-managed metadata file recording which template version a folder was
# created from. Distinctly named so it cannot collide with any version file
# make_cv itself may define later; trivially renamed to match that format
# if/when it exists.
SCAFFOLD_VERSION_FILE = '.scaffold_version'


def _template_commit(template):
    """Current commit hash of the scaffold template clone, or 'unknown' if
    it cannot be determined (not a git repo, git unavailable). Never raises
    and never blocks: the stamp is bookkeeping, not the critical path —
    hence the timeout on even this instant local command."""
    try:
        out = subprocess.run(
            ['git', '-C', template, 'rev-parse', 'HEAD'],
            capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return 'unknown'


def _write_scaffold_version(dest, template):
    """Record the template version this folder was created from."""
    lines = [
        '# Scaffold template version this folder was created from '
        '(app-managed).',
        f'commit = {_template_commit(template)}',
        f"created = {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    ]
    path = os.path.join(dest, SCAFFOLD_VERSION_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def read_scaffold_version(professor_folder):
    """Commit hash recorded when the folder was created, or None if the
    stamp is absent or unreadable. This is the hook for the future
    version check (compare against the template before generating) and
    for propagation ("which folders are behind?")."""
    path = os.path.join(professor_folder, SCAFFOLD_VERSION_FILE)
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                key, sep, value = line.partition('=')
                if sep and key.strip() == 'commit':
                    return value.strip() or None
    except OSError:
        return None
    return None


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------

def ensure_professor_folder(professor_key, first_name, last_name, email,
                            google_id=None, orcid=None, scopus_id=None):
    """
    Make sure a professor's on-disk folder exists.

    Returns 'exists' (folder already present — untouched) or 'created'
    (built from the scaffold template with personal files patched).
    Raises FolderCreationError on failure, after removing any partial copy.
    """
    template = current_app.config.get('SCAFFOLD_TEMPLATE', '')
    root = current_app.config.get('PROFESSORS_ROOT', '')

    dest = os.path.join(root, folder_name_for(professor_key))
    if os.path.exists(dest):
        return 'exists'

    if not template or not os.path.isdir(template):
        raise FolderCreationError(
            f"Scaffold template not found at {template!r} — check the "
            f"'scaffold_template' path in config.yml")
    if not root or not os.path.isdir(root):
        raise FolderCreationError(
            f"Professors root not found at {root!r} — check the "
            f"'professors_root' path in config.yml")

    try:
        # Professor folders are data, not clones: .git stays behind, and
        # scaffolding updates flow through the app's template, not git.
        shutil.copytree(template, dest,
                        ignore=shutil.ignore_patterns('.git'))

        personal = os.path.join(dest, 'make_cv', 'PersonalData')
        write_personal_data(
            os.path.join(personal, 'personal_data.txt'),
            google_id, orcid, scopus_id)
        render_contactinfo(
            os.path.join(personal, 'ContactInfo.tex'),
            first_name, last_name, email)
        disable_stats_flags(dest)
        _write_scaffold_version(dest, template)

        return 'created'
    except Exception as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise FolderCreationError(str(exc)) from exc
