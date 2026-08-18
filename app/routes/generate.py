# app/routes/generate.py
# Phase 5 - FAR/CV generation route

import os
import shutil
import tempfile
import traceback
from datetime import datetime

from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, send_file, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.utils import execute_query, safe_slug
from app.excel_export import export_all
from app.accounts import ensure_folder_for_existing, refresh_personal_files

generate_bp = Blueprint('generate', __name__)


def professor_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('professor', 'admin'):
            flash('Access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# Folder naming lives in the folder-creation service so that path
# resolution (here) and folder creation share one definition.
from app.folder_service import folder_name_for as _folder_name_for


def write_bib_from_db(professor_key, professor_folder):
    """
    Rebuild Scholarship/scholarship.bib from the PUBLICATIONS table —
    each entry's RawBibtex verbatim, markers and all fields intact.
    Zero publications leaves whatever .bib is already on disk (the
    template's), and any failure is logged and non-fatal.
    Shared by the generate flow and the data export (Issue #7).
    """
    bib_path = os.path.join(professor_folder, 'Scholarship', 'scholarship.bib')
    try:
        pub_rows = execute_query(
            'SELECT RawBibtex FROM PUBLICATIONS '
            'WHERE ProfessorKey=%s AND RawBibtex IS NOT NULL AND RawBibtex <> %s '
            'ORDER BY Year DESC, PublicationKey',
            (professor_key, ''),
        ) or []
        if pub_rows:
            os.makedirs(os.path.dirname(bib_path), exist_ok=True)
            with open(bib_path, 'w', encoding='utf-8') as bf:
                bf.write('\n\n'.join(r['RawBibtex'] for r in pub_rows))
                bf.write('\n')
            current_app.logger.info(
                f'Wrote {len(pub_rows)} publications to {bib_path} from DB'
            )
    except Exception as e:
        current_app.logger.warning(f'Could not write scholarship.bib from DB: {e}')
        # Non-fatal — fall back to whatever .bib is already on disk


def generated_name(base, last, first, date_str=None):
    """
    Per-professor filename for a generated output, so a file stays
    identifiable once detached from any zip:
      ('far.pdf', 'Thugudam', 'Akshay') -> 'far_thugudam_akshay_20260725.pdf'
    Applied at packaging time only — files on disk keep make_cv's names.
    """
    stem, ext = os.path.splitext(base)
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    return f"{stem}_{safe_slug(last)}_{safe_slug(first)}_{date_str}{ext}"


# Regenerated on every run; must not travel in a data export.
EXPORT_EXCLUDED_SUFFIXES = ('.aux', '.log', '.out', '.toc', '.bbl',
                            '.bcf', '.blg', '.run.xml')
EXPORT_EXCLUDED_DIRS = {'Tables_far'}


class ExportError(Exception):
    """The professor's data could not be packaged for download."""


def build_export_zip(professor_key):
    """
    Package a professor's folder as an in-memory zip, REFRESHED from the
    database first so the export always carries current data — even for
    a professor who has never generated (Issue #7).

    Sequence: heal the folder if missing -> rebuild scholarship.bib from
    PUBLICATIONS -> write all Excel files from the DB -> zip everything
    except LaTeX build artifacts.

    Returns (BytesIO, download_name). Raises ExportError with a
    human-readable message on failure.
    """
    import io
    import zipfile

    from app.utils import safe_slug

    prof = execute_query(
        'SELECT FirstName, LastName FROM PROFESSOR WHERE ProfessorKey = %s',
        (professor_key,), fetchone=True)
    if not prof:
        raise ExportError('Professor not found.')

    status, heal_error = ensure_folder_for_existing(professor_key)
    if heal_error:
        raise ExportError(
            f'Your data folder could not be set up: {heal_error}')

    professor_folder = os.path.join(
        current_app.config['PROFESSORS_ROOT'],
        _folder_name_for(professor_key))

    # Refresh disk from DB truth — the step that makes the export honest.
    refresh_personal_files(professor_key, professor_folder)
    write_bib_from_db(professor_key, professor_folder)
    try:
        db_data = fetch_all_db_data(professor_key)
        export_all(professor_key, professor_folder, db_data)
    except Exception as e:
        current_app.logger.error(
            f'Export refresh failed for professor {professor_key}: {e}')
        raise ExportError(f'Could not refresh your data files: {e}')

    slug = (f"far_data_{safe_slug(prof.get('LastName'))}"
            f"_{safe_slug(prof.get('FirstName'))}")
    download_name = f"{slug}_{datetime.now().strftime('%Y%m%d')}.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(professor_folder):
            dirs[:] = [d for d in dirs if d not in EXPORT_EXCLUDED_DIRS]
            for fname in files:
                if fname.endswith(EXPORT_EXCLUDED_SUFFIXES):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, professor_folder)
                zf.write(full, os.path.join(slug, rel))
    buf.seek(0)
    return buf, download_name


def get_professor_folder(professor_key):
    """
    Returns (folder_path, professor_row) for a professor.
    Format: <PROFESSORS_ROOT>/<ProfessorKey>

    The folder is addressed by the immutable ProfessorKey only — never by
    name or department, which can change and would break the path.
    Returns (None, None) if the professor does not exist.
    """
    prof = execute_query(
        "SELECT FirstName, LastName, Department FROM PROFESSOR WHERE ProfessorKey = %s",
        (professor_key,), fetchone=True
    )
    if not prof:
        return None, None

    professors_root = current_app.config.get('PROFESSORS_ROOT', '')
    professor_folder = os.path.join(professors_root, _folder_name_for(professor_key, prof))
    return professor_folder, prof


def fetch_all_db_data(professor_key):
    """Fetch all data for a professor from the DB."""
    pk = professor_key

    def q(sql, params=None):
        try:
            return execute_query(sql, params or (pk,)) or []
        except Exception as e:
            current_app.logger.warning(f"Query failed: {e}")
            return []

    # Personal awards: join PERSONALAWARDS with AWARDS
    personal_awards = q("""
        SELECT a.Title, a.Year, a.`Award Type`, pa.Amount
        FROM PERSONALAWARDS pa
        JOIN AWARDS a ON pa.`Award Key` = a.`Award Key`
        WHERE pa.ProfessorKey = %s
    """)

    # Student awards, scoped directly by owner
    student_awards = q("""
        SELECT a.Title, a.Year, a.`Award Type`, sa.Student, sa.Amount, sa.Category
        FROM STUDENTAWARDS sa
        JOIN AWARDS a ON sa.`Award Key` = a.`Award Key`
        WHERE sa.ProfessorKey = %s
    """)

    proposals = q("""SELECT `Proposal ID`, Role, `Funded?`, `Principal Investigator`,
        Title, `Begin Date`, `End Date`, Sponsor, `Allocated Amount`,
        `Submit Date`, Faculty, `Total Cost` FROM PROPOSAL WHERE ProfessorKey = %s""")
    grants = q("""SELECT `Grant ID`, Role, PCT, `Principal Investigators`,
        Title, `Begin Date`, `End Date`, Sponsor, `Allocated Amount`,
        `Award Total Direct Funding`, Faculty, `Total Cost` FROM GRANTS WHERE ProfessorKey = %s""")
    expenditures = q("""SELECT Year, Name, Expenditure, Indirect, Tuition,
        `Salary Recovery` FROM EXPENDITURE WHERE ProfessorKey = %s""")
    current_students = q("""SELECT `Student Name`, `Current Program`,
        `Start Date` FROM CURRENTSTUDENTS WHERE ProfessorKey = %s""")
    thesis = q("""SELECT `Student Name`, `Start Date`, Year, Degree,
        Advisor, Title, Comments FROM THESIS WHERE ProfessorKey = %s""")
    service = q("""SELECT Description, Type, Position, Term,
        `Calendar Year`, `Hours/Semester`, Comments FROM SERVICE WHERE ProfessorKey = %s""")
    reviews = q("""SELECT Journal, `Start Date`, Rounds
        FROM REVIEWS WHERE ProfessorKey = %s""")
    prof_dev = q("""SELECT Description, Type, Term, `Calendar Year`,
        Hours, Notes FROM PROFESSIONALDEVELOPMENT WHERE ProfessorKey = %s""")
    undergrad = q("""SELECT Students, Title, `Program Type`, Term,
        `Calendar Year` FROM UNDERGRADUATERESEARCH WHERE ProfessorKey = %s""")
    advisee = q("""SELECT `Advisor Name`, `Advisee Count`, Year, Term
        FROM ADVISEECOUNT WHERE ProfessorKey = %s""")
    advising = q("SELECT * FROM ADVISINGEVALUATION WHERE ProfessorKey = %s")
    teaching = q("""SELECT Term, `Combined Course Number`, `Course Section`,
        `Course Title`, Enrolment, `Count Evals`,
        `Calculated Mean`, `Weighted Average`
        FROM TEACHINGEVALUATION
        WHERE ProfessorKey = %s
        AND `Combined Course Number` IS NOT NULL
        AND `Count Evals` IS NOT NULL
        AND `Count Evals` > 0
        GROUP BY Term, `Combined Course Number`, `Course Section`,
        `Course Title`, Enrolment, `Count Evals`,
        `Calculated Mean`, `Weighted Average`""")
    prospective = q("""SELECT Staff, Year, Visits, Deposits
        FROM PROSPECTIVEVISIT WHERE ProfessorKey = %s""")

    return {
        'personal_awards':  personal_awards,
        'student_awards':   student_awards,
        'proposals':        proposals,
        'grants':           grants,
        'expenditures':     expenditures,
        'current_students': current_students,
        'thesis':           thesis,
        'service':          service,
        'reviews':          reviews,
        'prof_development': prof_dev,
        'undergrad_research': undergrad,
        'advisee_counts':   advisee,
        'advising_evals':   advising,
        'teaching':         teaching,
        'prospective_visits': prospective,
    }


def ensure_config_updated(far_folder, options=None):
    """
    Auto-update make_cv.cfg in the given folder so it has all required keys.
    Optionally applies user-selected options from the Generate page.

    options dict keys (all optional):
        years               int  — number of years (-1 = all)
        includestudentmarkers  bool
        includecitationcounts  bool
        shortteachingtable     bool
        hideteachingevals      bool
        excluded_sections   list — section names to set False
    """
    import configparser
    cfg_path = os.path.join(far_folder, 'make_cv.cfg')
    folder_kind = os.path.basename(os.path.normpath(far_folder))

    try:
        from make_cv.create_config import create_config, verify_config

        if not os.path.exists(cfg_path):
            # Create it HERE rather than deferring to make_far, whose own
            # create_config at generation time is unguarded — it would
            # plant the same defaults the guard below exists to defuse.
            current_dir = os.getcwd()
            os.chdir(far_folder)
            try:
                create_config('make_cv.cfg', configparser.ConfigParser())
                current_app.logger.info(
                    f'Created make_cv.cfg in {far_folder}')
            finally:
                os.chdir(current_dir)

        # Read the existing config
        old_config = configparser.ConfigParser()
        old_config.read(cfg_path)

        # Update if keys are missing
        if not verify_config(old_config):
            current_dir = os.getcwd()
            os.chdir(far_folder)
            try:
                create_config('make_cv.cfg', old_config)
                current_app.logger.info(f'Updated make_cv.cfg in {far_folder}')
                old_config = configparser.ConfigParser()
                old_config.read(cfg_path)
            finally:
                os.chdir(current_dir)

        # ------------------------------------------------------------
        # THE FAR CONFIG GUARD (batch hangs of 2026-07-30).
        #
        # create_config's defaults plant two mines in a FAR config:
        #   GoogleStats/ScopusStats=true -> per-publication citation
        #     scrape with no timeout upstream (the hang);
        #   References=false -> a CV-only section FAR.sty never
        #     declares, so LaTeX errors — and make_far's missing
        #     -interaction=batchmode turns that error into a ? prompt
        #     waiting forever for keyboard input.
        # Both fired live, from one config repair, freezing the batch
        # twice. CV configs are left alone: a CV legitimately excludes
        # its References section.
        # ------------------------------------------------------------
        sec0 = list(old_config.sections())[0] if old_config.sections() else 'CV'
        latexfile = old_config.get(sec0, 'latexfile', fallback='')
        is_far = (latexfile.lower().startswith('far')
                  or folder_kind.upper().startswith('FAR'))
        if is_far:
            if latexfile.lower() != 'far.tex':
                old_config.set(sec0, 'latexfile', 'far.tex')
            old_config.set(sec0, 'references', 'true')
            old_config.set(sec0, 'googlestats', 'false')
            old_config.set(sec0, 'scopusstats', 'false')

        # Apply user options if provided
        if options:
            section = list(old_config.sections())[0] if old_config.sections() else 'CV'

            # Years (-1 = all, positive = last N years)
            if 'years' in options:
                old_config.set(section, 'years', str(options['years']))

            # Display options
            for key in ('includestudentmarkers', 'includecitationcounts',
                        'shortteachingtable', 'hideteachingevals'):
                if key in options:
                    old_config.set(section, key, 'true' if options[key] else 'false')

            # Section toggles — set excluded sections to false, rest to true
            all_sections = [
                'journal', 'arxiv', 'refereed', 'book', 'patent',
                'conference', 'invited', 'grants', 'proposals', 'teaching',
                'service', 'reviews', 'profdevelopment', 'studentawards',
                'personalawards', 'gradadvisees', 'undergradresearch',
            ]
            excluded = options.get('excluded_sections', [])
            for sec in all_sections:
                val = 'false' if sec in excluded else 'true'
                if old_config.has_option(section, sec):
                    old_config.set(section, sec, val)

            current_app.logger.info(f'Applied user options to make_cv.cfg in {far_folder}')

        # Persist ALWAYS, not only when options were supplied. The guard
        # above sets values in memory; without an unconditional write they
        # were discarded on every call that passed no options — which is
        # every call from batch and export.
        with open(cfg_path, 'w') as f:
            old_config.write(f)

    except Exception as e:
        current_app.logger.warning(f'Could not update make_cv.cfg: {e}')


def check_prerequisites(professor_folder, fmt):
    """
    Check everything needed for generation BEFORE running make_far.
    Returns a list of error messages. Empty list means all good.

    WHY WE CHECK EARLY:
    make_far takes 10-30 seconds to run. If we check prerequisites first,
    we can give the user a clear error message immediately instead of
    waiting 30 seconds for a cryptic crash message.
    """
    errors = []

    # Check 1: Does the make_cv folder exist?
    make_cv_folder = os.path.join(professor_folder, 'make_cv')
    if not os.path.isdir(make_cv_folder):
        errors.append(
            'Your make_cv folder is not set up. '
            'Please ask your administrator to run "make_cv -b" for your profile.'
        )
        return errors  # No point checking further

    # Check 2: Is LaTeX installed? (required for PDF)
    if fmt in ('pdf', 'both'):
        import shutil
        if not shutil.which('xelatex'):
            errors.append(
                'LaTeX (xelatex) is not installed on this server. '
                'PDF generation requires LaTeX. Contact your administrator.'
            )

    # Check 3: Is pandoc installed? (required for Word)
    if fmt in ('docx', 'both'):
        import shutil
        if not shutil.which('pandoc'):
            errors.append(
                'Pandoc is not installed on this server. '
                'Word (.docx) generation requires pandoc. Contact your administrator.'
            )

    # Check 4: Does the FAR folder exist?
    far_folder = os.path.join(make_cv_folder, 'FAR')
    far_docx_folder = os.path.join(make_cv_folder, 'FAR_docx')
    cv_folder = os.path.join(make_cv_folder, 'CV')

    if fmt in ('pdf', 'both') and not os.path.isdir(far_folder):
        errors.append(
            'FAR template folder not found. '
            'Please ask your administrator to set up your make_cv folder.'
        )

    if fmt in ('docx', 'both') and not os.path.isdir(far_docx_folder):
        errors.append(
            'FAR_docx template folder not found. '
            'Please ask your administrator to set up your make_cv folder.'
        )

    return errors


def translate_error(raw_error):
    """
    Convert cryptic make_far/Python error messages into friendly ones.

    WHY THIS EXISTS:
    make_far produces technical error messages like:
        "KeyError: 'count_19'"
        "FileNotFoundError: [Errno 2] No such file or directory: 'far.tex'"
    These mean nothing to a professor. We translate them into
    plain English that tells the user what to do.
    """
    err = str(raw_error).lower()

    if 'latex' in err or 'xelatex' in err or 'tex' in err:
        return (
            'LaTeX compilation failed. This usually means a data issue. '
            'Check that your data does not contain special characters (&, %, $, #). '
            'Contact your administrator if this continues.'
        )
    if 'pandoc' in err:
        return (
            'Pandoc failed to convert the document to Word format. '
            'Contact your administrator.'
        )
    if 'no such file' in err or 'filenotfounderror' in err:
        return (
            'A required template file is missing. '
            'Please ask your administrator to check your make_cv folder setup.'
        )
    if 'keyerror' in err or 'column' in err:
        return (
            'A data formatting error occurred. '
            'The error has been logged. Contact your administrator.'
        )
    if 'permission' in err:
        return (
            'Permission error — the server cannot write files to your data folder. '
            'Contact your administrator.'
        )

    # Default — show a generic message but log the real error
    return (
        'Generation failed due to an unexpected error. '
        'The error has been logged. Contact your administrator at far@clarkson.edu.'
    )


GENERATION_TIMEOUT_DEFAULT = 300  # seconds


def _generation_command(module, extra_args=()):
    """The command list that launches a generator as a subprocess.
    Separated out so tests can substitute tiny fake scripts."""
    import sys
    # -u: unbuffered. A python child writing into a pipe block-buffers
    # its prints, so progress arrives inverted (grandchildren first) and
    # a HUNG child's lines are lost entirely — exactly when the timeout
    # report needs them. Proven live 2026-08-17.
    return [sys.executable, '-u', '-m', module, *extra_args]


def _run_generation(module, folder, extra_args=(), what='generation'):
    """
    Issue #12: run a generator (make_far / make_cv) as a SUBPROCESS with
    a hard timeout, instead of importing it in-process.

    In-process, a hang inside the generator — LaTeX waiting at a "?"
    prompt for keyboard input, a network call with no limit — is a hang
    inside the web worker: the app cannot notice, log, or recover. Both
    happened live on 2026-07-30 and froze the batch until Ctrl-C.

    As a subprocess the app keeps control: it watches the clock, kills
    the process at the budget, and reports a timeout. Output is captured
    so a failure's actual error text reaches the results table instead
    of scattering into a console nobody is watching.

    Returns (success, error_message) — the same contract as before, so
    every caller (single generate, batch, standalone) is unchanged.
    """
    import subprocess

    try:
        timeout = current_app.config.get('GENERATION_TIMEOUT',
                                         GENERATION_TIMEOUT_DEFAULT)
    except RuntimeError:  # outside an app context
        timeout = GENERATION_TIMEOUT_DEFAULT

    import threading

    cmd = _generation_command(module, extra_args)
    captured = []
    try:
        # stderr merged into stdout: one stream, lines in order, and
        # error text can never be lost in a separate pipe.
        # start_new_session: the child gets its own process group, so a
        # timeout can kill the WHOLE tree. The likeliest hanger is a
        # grandchild (xelatex at its ? prompt); killing only the middle
        # python would orphan it, still holding far.pdf.
        proc = subprocess.Popen(cmd, cwd=folder, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                bufsize=1, start_new_session=True)
    except Exception as e:
        return False, str(e)

    def _pump():
        # Show it AND capture it: relay each line to the app's console
        # the moment it arrives, and keep a copy for error reporting.
        for line in proc.stdout:
            print(line, end='', flush=True)
            captured.append(line)

    pump = threading.Thread(target=_pump, daemon=True)
    pump.start()

    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.wait()
        pump.join(timeout=5)
        tail = ''.join(captured)[-1500:].strip()
        return False, (
            f'{what} timed out after {timeout}s and was stopped. This '
            f'usually means LaTeX hit an error and waited for keyboard '
            f'input, or a network call hung.'
            + (f' Last output before the stop:\n{tail}' if tail else ''))

    pump.join(timeout=5)
    if rc != 0:
        output = ''.join(captured).strip()
        tail = output[-1500:] if output else f'exit status {rc}'
        return False, tail
    return True, None


def run_make_far(far_folder, use_pandoc=False):
    """Generate a FAR in far_folder. Returns (success, error_message)."""
    extra = ('-p',) if use_pandoc else ()
    return _run_generation('make_cv.make_far', far_folder, extra,
                           what='FAR generation')


def run_make_cv(cv_folder):
    """Generate a CV in cv_folder. Returns (success, error_message)."""
    return _run_generation('make_cv.make_cv', cv_folder,
                           what='CV generation')


@generate_bp.route('/generate', methods=['GET', 'POST'])
@login_required
@professor_required
def generate():
    """Professor-facing generation page."""
    if request.method == 'POST':
        doc_type   = request.form.get('doc_type', 'far')   # far | cv
        years      = request.form.get('years', '1')         # 1,2,3,5,0(all)
        fmt        = request.form.get('format', 'pdf')      # pdf | docx | both
        bib_file   = request.files.get('bib_file')

        # Build options dict from form
        years_int = int(years) if years != '0' else -1
        excluded_sections = request.form.getlist('excluded_sections')
        options = {
            'years':                  years_int,
            'includestudentmarkers':  'includestudentmarkers'  in request.form,
            'includecitationcounts':  'includecitationcounts'  in request.form,
            'shortteachingtable':     'shortteachingtable'     in request.form,
            'hideteachingevals':      'hideteachingevals'      in request.form,
            'excluded_sections':      excluded_sections,
        }

        pk = current_user.professor_key
        professor_folder, prof = get_professor_folder(pk)

        if not professor_folder:
            flash('Professor profile not found.', 'danger')
            return redirect(url_for('generate.generate'))

        if not os.path.isdir(professor_folder):
            # Self-healing: the folder may never have been created (for
            # example, the decoupled attempt at registration failed).
            # Build it now from the scaffold template instead of sending
            # the professor to an administrator.
            status, heal_error = ensure_folder_for_existing(pk)
            if heal_error:
                flash(f'Your data folder could not be set up: {heal_error}',
                      'danger')
                return redirect(url_for('generate.generate'))
            current_app.logger.info(
                'Healed missing folder for professor %s (%s)', pk, status)

        # Check prerequisites BEFORE running make_far
        # This gives clear error messages immediately instead of
        # waiting 30 seconds for a cryptic crash
        prereq_errors = check_prerequisites(professor_folder, fmt)
        if prereq_errors:
            for err in prereq_errors:
                flash(err, 'danger')
            return redirect(url_for('generate.generate'))

        # ContactInfo/personal_data are derived from the DB, like the bib
        # and the spreadsheets — refresh them every run, regardless of
        # whether the professor uploaded their own .bib below.
        refresh_personal_files(pk, professor_folder)

        # Provide scholarship.bib for make_cv.
        bib_path = os.path.join(professor_folder, 'Scholarship', 'scholarship.bib')
        if bib_file and bib_file.filename.endswith('.bib'):
            # A fresh .bib was uploaded on this request — use it verbatim.
            os.makedirs(os.path.dirname(bib_path), exist_ok=True)
            bib_file.save(bib_path)
        else:
            # No upload — rebuild scholarship.bib from the DB so that any edits
            # the professor made on the Publications page are reflected in the
            # FAR. (Shared with the data export — see write_bib_from_db.)
            write_bib_from_db(pk, professor_folder)

        # Fetch DB data and write Excel files
        try:
            db_data = fetch_all_db_data(pk)
            export_all(pk, professor_folder, db_data)
        except Exception as e:
            flash(f'Error exporting data: {e}', 'danger')
            current_app.logger.error(traceback.format_exc())
            return redirect(url_for('generate.generate'))

        # Determine output folder and run make_far / make_cv
        make_cv_folder = os.path.join(professor_folder, 'make_cv')
        output_files   = []
        errors         = []

        if doc_type in ('far', 'both'):
            if fmt in ('pdf', 'both'):
                far_folder = os.path.join(make_cv_folder, 'FAR')
                ensure_config_updated(far_folder, options)   # silently fix missing config keys
                ok, err = run_make_far(far_folder, use_pandoc=False)
                if ok:
                    pdf = os.path.join(far_folder, 'far.pdf')
                    if os.path.exists(pdf):
                        output_files.append((generated_name('far.pdf', prof['LastName'], prof['FirstName']), pdf))
                else:
                    current_app.logger.error(f'FAR PDF error: {err}')
                    errors.append(translate_error(err))

            if fmt in ('docx', 'both'):
                far_docx_folder = os.path.join(make_cv_folder, 'FAR_docx')
                ensure_config_updated(far_docx_folder, options)  # silently fix missing config keys
                ok, err = run_make_far(far_docx_folder, use_pandoc=True)
                if ok:
                    docx = os.path.join(far_docx_folder, 'far.docx')
                    if os.path.exists(docx):
                        output_files.append((generated_name('far.docx', prof['LastName'], prof['FirstName']), docx))
                else:
                    current_app.logger.error(f'FAR docx error: {err}')
                    errors.append(translate_error(err))

        if doc_type in ('cv', 'both'):
            cv_folder = os.path.join(make_cv_folder, 'CV')
            ensure_config_updated(cv_folder, options)        # silently fix any missing config keys
            ok, err = run_make_cv(cv_folder)
            if ok:
                pdf = os.path.join(cv_folder, 'cv.pdf')
                if os.path.exists(pdf):
                    output_files.append((generated_name('cv.pdf', prof['LastName'], prof['FirstName']), pdf))
            else:
                current_app.logger.error(f'CV error: {err}')
                errors.append(translate_error(err))

        if errors:
            for e in errors:
                flash(e, 'danger')

        if not output_files:
            if not errors:
                # No errors were reported but no files were generated either
                # This means make_far ran but produced no output
                flash(
                    'Generation completed but no output files were produced. '
                    'This may be a LaTeX compilation issue. '
                    'Contact your administrator at far@clarkson.edu.',
                    'danger'
                )
            return redirect(url_for('generate.generate'))

        # Package output into a zip and send
        tmp_dir  = tempfile.mkdtemp()
        zip_name = f"FAR_{safe_slug(prof['LastName'])}_{datetime.now().strftime('%Y%m%d')}"
        zip_path = os.path.join(tmp_dir, zip_name)

        import zipfile
        with zipfile.ZipFile(zip_path + '.zip', 'w') as zf:
            for filename, filepath in output_files:
                zf.write(filepath, filename)

        response = send_file(
            zip_path + '.zip',
            as_attachment=True,
            download_name=f'{zip_name}.zip',
            mimetype='application/zip'
        )
        response.set_cookie('fileDownload', 'true', max_age=60)
        return response

    return render_template('professor/generate.html')


@generate_bp.route('/admin/generate-all', methods=['GET', 'POST'])
@login_required
def generate_all():
    """Admin batch generation for all professors."""
    if current_user.role != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        years  = request.form.get('years', '1')
        fmt    = request.form.get('format', 'pdf')

        professors = execute_query("SELECT ProfessorKey, FirstName, LastName, Department FROM PROFESSOR") or []

        # THE STATS-HANG LAW, applied to batch.
        #
        # The stats fetch (Google Scholar / Scopus citation scraping,
        # one lookup per publication, NO timeout upstream) is gated by
        # the GoogleStats/ScopusStats keys in make_cv.cfg. Folder
        # creation sets them false — but ensure_config_updated repairs
        # an old cfg by running make_cv's create_config, whose DEFAULTS
        # for those keys are TRUE. So the repair step re-arms the very
        # landmine creation defuses: one professor with an ancient cfg
        # stalls the batch on a per-publication scrape, and everyone
        # after them never gets generated. Observed live 2026-07-30
        # ("UseWebScraper is missing from config file" ... hang).
        #
        # Batch therefore disables the stats flags AFTER every config
        # update, using the same tested patcher creation uses. A
        # professor who wants citation counts can generate alone and
        # wait for their own fetch.
        batch_options = {
            'years': int(years) if years != '0' else -1,
        }

        tmp_dir  = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_dir, 'all_fars.zip')
        results  = []

        import zipfile
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for prof in professors:
                pk     = prof['ProfessorKey']
                name    = f"{prof['LastName']}, {prof['FirstName']}"
                arc_dir = f"{safe_slug(prof['LastName'])}_{safe_slug(prof['FirstName'])}"

                # Every professor gets exactly ONE row in the report,
                # whatever happens to them. A name missing from this table
                # would mean the report is broken, not the professor — and
                # an admin has no way to notice an absence.
                notes = []

                try:
                    # Heal first, exactly as the single-generation route
                    # does: a professor who signed up but never logged in
                    # has no folder, and rebuilding it is automatic.
                    status, heal_error = ensure_folder_for_existing(pk)
                    professor_folder, _ = get_professor_folder(pk)

                    if not professor_folder or not os.path.isdir(professor_folder):
                        reason = f': {heal_error}' if heal_error else ''
                        results.append({'name': name,
                                        'status': f'❌ no folder and healing failed{reason}'})
                        continue
                    if heal_error:
                        # Folder exists but healing complained — worth a note
                        # on this professor's row rather than silence.
                        notes.append(f'⚠️ folder: {heal_error}')

                    # Refresh disk from DB truth — the same three steps the
                    # single route performs. write_bib_from_db was missing
                    # here, so batch FARs were built from whatever bib
                    # happened to be on disk, silently omitting every
                    # publication added through the web app.
                    refresh_personal_files(pk, professor_folder)
                    write_bib_from_db(pk, professor_folder)
                    db_data = fetch_all_db_data(pk)
                    export_all(pk, professor_folder, db_data)
                except Exception as e:
                    # Covers healing, the personal-file refresh, the bib
                    # rebuild, and the Excel export — everything before
                    # make_far runs.
                    results.append({'name': name, 'status': f'❌ preparation failed: {e}'})
                    continue

                make_cv_folder = os.path.join(professor_folder, 'make_cv')

                try:
                    if fmt in ('pdf', 'both'):
                        far_folder = os.path.join(make_cv_folder, 'FAR')
                        ensure_config_updated(far_folder, batch_options)
                        ok, err = run_make_far(far_folder, use_pandoc=False)
                        pdf = os.path.join(far_folder, 'far.pdf')
                        if ok and os.path.exists(pdf):
                            zf.write(pdf, f"{arc_dir}/{generated_name('far.pdf', prof['LastName'], prof['FirstName'])}")
                            notes.append('✅ PDF generated')
                        elif ok:
                            notes.append('❌ PDF: make_far reported success but no file was produced')
                        else:
                            notes.append(f'❌ PDF: {err}')

                    if fmt in ('docx', 'both'):
                        far_docx = os.path.join(make_cv_folder, 'FAR_docx')
                        ensure_config_updated(far_docx, batch_options)
                        ok, err = run_make_far(far_docx, use_pandoc=True)
                        docx = os.path.join(far_docx, 'far.docx')
                        if ok and os.path.exists(docx):
                            zf.write(docx, f"{arc_dir}/{generated_name('far.docx', prof['LastName'], prof['FirstName'])}")
                            notes.append('✅ Word generated')
                        elif ok:
                            notes.append('❌ Word: make_far reported success but no file was produced')
                        else:
                            notes.append(f'❌ Word: {err}')
                except Exception as e:
                    notes.append(f'❌ generation error: {e}')

                results.append({'name': name,
                                'status': ' · '.join(notes) or '❌ nothing was generated'})

        return render_template('admin/generate_all.html',
                               results=results,
                               zip_path=zip_path)

    return render_template('admin/generate_all.html', results=None)


@generate_bp.route('/admin/download-all-fars')
@login_required
def download_all_fars():
    """Download the batch generated zip."""
    if current_user.role != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('auth.login'))

    zip_path = request.args.get('path', '')
    if not zip_path or not os.path.exists(zip_path):
        flash('File not found.', 'danger')
        return redirect(url_for('generate.generate_all'))

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f'all_fars_{datetime.now().strftime("%Y%m%d")}.zip',
        mimetype='application/zip'
    )
