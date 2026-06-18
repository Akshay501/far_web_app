# app/routes/standalone.py
# FAR Universal (Standalone Mode) — Routes
#
# No login required. Professor uploads their make_cv folder as a zip,
# edits data through web forms, generates FAR/CV, and downloads everything.
# Temp folder is deleted after download.

import os
import shutil
import tempfile
import zipfile
import uuid
from datetime import datetime

from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, send_file, session, current_app,
                   jsonify)

from app.standalone_excel import (
    get_file_inventory,
    read_grants, append_grant, update_grant, delete_grant, duplicate_grant,
    read_proposals, append_proposal, update_proposal, delete_proposal, duplicate_proposal,
    read_service, append_service, update_service, delete_service, duplicate_service,
    read_personal_awards, append_personal_award, update_personal_award, delete_personal_award, duplicate_personal_award,
    read_student_awards, append_student_award, update_student_award, delete_student_award, duplicate_student_award,
    read_current_students, append_current_student, update_current_student, delete_current_student, duplicate_current_student,
    read_thesis, append_thesis, update_thesis, delete_thesis, duplicate_thesis,
    read_teaching,
)

standalone_bp = Blueprint('standalone', __name__, url_prefix='/standalone')

AWARD_TYPES = ['University', 'Department', 'School', 'Professional', 'Community']
DEGREE_TYPES = ['PhD', 'MS', 'BS', 'BS Honors', 'Other']
SERVICE_TYPES = ['Committee Work', 'Journal Review', 'Outreach/Seminar',
                 'University Committee', 'Accreditation', 'Other']


def get_folder():
    """
    Get the professor's temp folder from the session.
    Returns None if no folder is set (professor hasn't uploaded yet).
    """
    folder = session.get('standalone_folder')
    if folder and os.path.isdir(folder):
        return folder
    return None


def require_folder():
    """
    Decorator-like helper — if no folder, redirect to upload page.
    Use at start of every route that needs the uploaded folder.
    """
    folder = get_folder()
    if not folder:
        flash('Please upload your make_cv folder first.', 'warning')
        return redirect(url_for('standalone.index'))
    return folder


# ─── Landing page & Upload ────────────────────────────────────────────────────

@standalone_bp.route('/')
def index():
    """Landing page — shows upload button."""
    # If they already have a session, go to dashboard
    if get_folder():
        return redirect(url_for('standalone.dashboard'))
    return render_template('standalone/index.html')


@standalone_bp.route('/upload', methods=['POST'])
def upload():
    """
    Professor uploads their make_cv folder as a zip.
    We extract it to a unique temp folder and store the path in the session.
    """
    if 'zip_file' not in request.files:
        flash('No file selected. Please choose a zip file.', 'danger')
        return redirect(url_for('standalone.index'))

    zip_file = request.files['zip_file']

    if not zip_file.filename.endswith('.zip'):
        flash('Please upload a .zip file.', 'danger')
        return redirect(url_for('standalone.index'))

    # Generate a unique session ID for this professor's temp folder
    session_id = str(uuid.uuid4())
    temp_base = tempfile.gettempdir()
    temp_folder = os.path.join(temp_base, f'far_standalone_{session_id}')
    os.makedirs(temp_folder, exist_ok=True)

    # Save and extract the zip
    zip_path = os.path.join(temp_folder, 'upload.zip')
    try:
        zip_file.save(zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_folder)
        os.remove(zip_path)  # clean up the zip itself
    except zipfile.BadZipFile:
        shutil.rmtree(temp_folder, ignore_errors=True)
        flash('The uploaded file is not a valid zip file.', 'danger')
        return redirect(url_for('standalone.index'))
    except Exception as e:
        shutil.rmtree(temp_folder, ignore_errors=True)
        flash(f'Error extracting zip file: {e}', 'danger')
        return redirect(url_for('standalone.index'))

    # Find the actual professor folder inside the extracted content
    # The zip might contain a top-level folder (e.g. "Thugu, Akshay/")
    # or the files might be directly at the root
    professor_folder = _find_professor_folder(temp_folder)

    # Store in session
    session['standalone_folder'] = professor_folder
    session['standalone_session_id'] = session_id
    session.permanent = True

    flash('Folder uploaded successfully! You can now edit your data.', 'success')
    return redirect(url_for('standalone.dashboard'))


def _find_professor_folder(temp_folder):
    """
    After extraction, find the actual professor folder.
    The zip might have been created from inside the folder (files at root)
    or from outside (one top-level folder containing everything).
    We detect this by checking if make_cv/ or Awards/ exists at root.
    """
    # Check if key folders exist directly at root
    for marker in ['make_cv', 'Awards', 'Service', 'Scholarship', 'Proposals & Grants']:
        if os.path.exists(os.path.join(temp_folder, marker)):
            return temp_folder  # files are at root

    # Otherwise, look for a single subdirectory (the professor folder)
    subdirs = [d for d in os.listdir(temp_folder)
               if os.path.isdir(os.path.join(temp_folder, d))
               and not d.startswith('__MACOSX')
               and not d.startswith('.')]

    if len(subdirs) == 1:
        return os.path.join(temp_folder, subdirs[0])

    # Couldn't determine — just use the temp folder
    return temp_folder


@standalone_bp.route('/reset')
def reset():
    """
    Clear the session and delete the temp folder.
    Professor can start fresh with a new upload.
    """
    folder = session.get('standalone_folder')
    if folder:
        # Find and delete the parent temp folder (far_standalone_<uuid>)
        parent = os.path.dirname(folder)
        if 'far_standalone_' in parent:
            shutil.rmtree(parent, ignore_errors=True)
        elif 'far_standalone_' in folder:
            shutil.rmtree(folder, ignore_errors=True)

    session.pop('standalone_folder', None)
    session.pop('standalone_session_id', None)
    flash('Session cleared. You can upload a new folder.', 'info')
    return redirect(url_for('standalone.index'))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@standalone_bp.route('/dashboard')
def dashboard():
    """
    Shows the professor what data files are available in their uploaded folder.
    """
    folder = get_folder()
    if not folder:
        return redirect(url_for('standalone.index'))

    inventory = get_file_inventory(folder)
    return render_template('standalone/dashboard.html', inventory=inventory)


# ─── Grants ───────────────────────────────────────────────────────────────────

@standalone_bp.route('/grants', methods=['GET', 'POST'])
def grants():
    folder = get_folder()
    if not folder:
        return redirect(url_for('standalone.index'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            append_grant(folder, request.form)
            flash('Grant added successfully.', 'success')
        elif action == 'delete':
            idx = int(request.form.get('row_idx', 0))
            delete_grant(folder, idx)
            flash('Grant deleted.', 'success')
        elif action == 'edit':
            idx = int(request.form.get('row_idx', 0))
            update_grant(folder, idx, request.form)
            flash('Grant updated successfully.', 'success')
            return redirect(url_for('standalone.grants') + f'?highlight=sa-grant-row-{idx}')
        elif action == 'duplicate':
            idx = int(request.form.get('row_idx', 0))
            rows = read_grants(folder)
            new_idx = len(rows)
            duplicate_grant(folder, idx)
            flash('Grant duplicated.', 'success')
            return redirect(url_for('standalone.grants') + f'?highlight=sa-grant-row-{new_idx}')
        return redirect(url_for('standalone.grants'))

    rows = read_grants(folder)
    return render_template('standalone/grants.html', rows=rows)


# ─── Proposals ────────────────────────────────────────────────────────────────

@standalone_bp.route('/proposals', methods=['GET', 'POST'])
def proposals():
    folder = get_folder()
    if not folder:
        return redirect(url_for('standalone.index'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            append_proposal(folder, request.form)
            flash('Proposal added successfully.', 'success')
        elif action == 'delete':
            idx = int(request.form.get('row_idx', 0))
            delete_proposal(folder, idx)
            flash('Proposal deleted.', 'success')
        elif action == 'edit':
            idx = int(request.form.get('row_idx', 0))
            update_proposal(folder, idx, request.form)
            flash('Proposal updated successfully.', 'success')
            return redirect(url_for('standalone.proposals') + f'?highlight=sa-proposal-row-{idx}')
        elif action == 'duplicate':
            idx = int(request.form.get('row_idx', 0))
            rows = read_proposals(folder)
            new_idx = len(rows)
            duplicate_proposal(folder, idx)
            flash('Proposal duplicated.', 'success')
            return redirect(url_for('standalone.proposals') + f'?highlight=sa-proposal-row-{new_idx}')
        return redirect(url_for('standalone.proposals'))

    rows = read_proposals(folder)
    return render_template('standalone/proposals.html', rows=rows)


# ─── Service ──────────────────────────────────────────────────────────────────

@standalone_bp.route('/service', methods=['GET', 'POST'])
def service():
    folder = get_folder()
    if not folder:
        return redirect(url_for('standalone.index'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            append_service(folder, request.form)
            flash('Service entry added successfully.', 'success')
        elif action == 'delete':
            idx = int(request.form.get('row_idx', 0))
            delete_service(folder, idx)
            flash('Service entry deleted.', 'success')
        elif action == 'edit':
            idx = int(request.form.get('row_idx', 0))
            update_service(folder, idx, request.form)
            flash('Service entry updated successfully.', 'success')
            return redirect(url_for('standalone.service') + f'?highlight=sa-service-row-{idx}')
        elif action == 'duplicate':
            idx = int(request.form.get('row_idx', 0))
            rows = read_service(folder)
            new_idx = len(rows)
            duplicate_service(folder, idx)
            flash('Service entry duplicated.', 'success')
            return redirect(url_for('standalone.service') + f'?highlight=sa-service-row-{new_idx}')
        return redirect(url_for('standalone.service'))

    rows = read_service(folder)
    return render_template('standalone/service.html',
                           rows=rows, service_types=SERVICE_TYPES)


# ─── Awards ───────────────────────────────────────────────────────────────────

@standalone_bp.route('/awards', methods=['GET', 'POST'])
def awards():
    folder = get_folder()
    if not folder:
        return redirect(url_for('standalone.index'))

    if request.method == 'POST':
        action = request.form.get('action')
        award_type_tab = request.form.get('award_tab', 'personal')

        if award_type_tab == 'personal':
            if action == 'add':
                append_personal_award(folder, request.form)
                flash('Personal award added.', 'success')
            elif action == 'delete':
                idx = int(request.form.get('row_idx', 0))
                delete_personal_award(folder, idx)
                flash('Personal award deleted.', 'success')
            elif action == 'edit':
                idx = int(request.form.get('row_idx', 0))
                update_personal_award(folder, idx, request.form)
                flash('Personal award updated.', 'success')
                return redirect(url_for('standalone.awards') + f'?highlight=sa-personal-row-{idx}')
            elif action == 'duplicate':
                idx = int(request.form.get('row_idx', 0))
                rows = read_personal_awards(folder)
                new_idx = len(rows)
                duplicate_personal_award(folder, idx)
                flash('Personal award duplicated.', 'success')
                return redirect(url_for('standalone.awards') + f'?highlight=sa-personal-row-{new_idx}')
        else:
            if action == 'add':
                append_student_award(folder, request.form)
                flash('Student award added.', 'success')
            elif action == 'delete':
                idx = int(request.form.get('row_idx', 0))
                delete_student_award(folder, idx)
                flash('Student award deleted.', 'success')
            elif action == 'edit':
                idx = int(request.form.get('row_idx', 0))
                update_student_award(folder, idx, request.form)
                flash('Student award updated.', 'success')
                return redirect(url_for('standalone.awards') + f'?tab=student&highlight=sa-student-row-{idx}')
            elif action == 'duplicate':
                idx = int(request.form.get('row_idx', 0))
                rows = read_student_awards(folder)
                new_idx = len(rows)
                duplicate_student_award(folder, idx)
                flash('Student award duplicated.', 'success')
                return redirect(url_for('standalone.awards') + f'?tab=student&highlight=sa-student-row-{new_idx}')
        tab_param = '?tab=student' if award_type_tab == 'student' else ''
        return redirect(url_for('standalone.awards') + tab_param)

    personal_awards = read_personal_awards(folder)
    student_awards = read_student_awards(folder)
    return render_template('standalone/awards.html',
                           personal_awards=personal_awards,
                           student_awards=student_awards,
                           award_types=AWARD_TYPES)


# ─── Scholarship ──────────────────────────────────────────────────────────────

@standalone_bp.route('/scholarship', methods=['GET', 'POST'])
def scholarship():
    folder = get_folder()
    if not folder:
        return redirect(url_for('standalone.index'))

    if request.method == 'POST':
        action = request.form.get('action')
        tab = request.form.get('scholarship_tab', 'students')

        if tab == 'students':
            if action == 'add':
                append_current_student(folder, request.form)
                flash('Current student added.', 'success')
            elif action == 'delete':
                idx = int(request.form.get('row_idx', 0))
                delete_current_student(folder, idx)
                flash('Student deleted.', 'success')
            elif action == 'edit':
                idx = int(request.form.get('row_idx', 0))
                update_current_student(folder, idx, request.form)
                flash('Student updated.', 'success')
                return redirect(url_for('standalone.scholarship') + f'?highlight=sa-student-row-{idx}')
            elif action == 'duplicate':
                idx = int(request.form.get('row_idx', 0))
                rows = read_current_students(folder)
                new_idx = len(rows)
                duplicate_current_student(folder, idx)
                flash('Student duplicated.', 'success')
                return redirect(url_for('standalone.scholarship') + f'?highlight=sa-student-row-{new_idx}')
        else:
            if action == 'add':
                append_thesis(folder, request.form)
                flash('Thesis added.', 'success')
            elif action == 'delete':
                idx = int(request.form.get('row_idx', 0))
                delete_thesis(folder, idx)
                flash('Thesis deleted.', 'success')
            elif action == 'edit':
                idx = int(request.form.get('row_idx', 0))
                update_thesis(folder, idx, request.form)
                flash('Thesis updated.', 'success')
                return redirect(url_for('standalone.scholarship') + f'?tab=thesis&highlight=sa-thesis-row-{idx}')
            elif action == 'duplicate':
                idx = int(request.form.get('row_idx', 0))
                rows = read_thesis(folder)
                new_idx = len(rows)
                duplicate_thesis(folder, idx)
                flash('Thesis duplicated.', 'success')
                return redirect(url_for('standalone.scholarship') + f'?tab=thesis&highlight=sa-thesis-row-{new_idx}')
        tab_param = '?tab=thesis' if tab == 'thesis' else ''
        return redirect(url_for('standalone.scholarship') + tab_param)

    current_students = read_current_students(folder)
    theses = read_thesis(folder)
    return render_template('standalone/scholarship.html',
                           current_students=current_students,
                           theses=theses,
                           degree_types=DEGREE_TYPES)


# ─── Teaching (read-only) ─────────────────────────────────────────────────────

@standalone_bp.route('/teaching')
def teaching():
    folder = get_folder()
    if not folder:
        return redirect(url_for('standalone.index'))
    rows = read_teaching(folder)
    return render_template('standalone/teaching.html', rows=rows)


# ─── Generate & Download ──────────────────────────────────────────────────────

@standalone_bp.route('/generate', methods=['GET', 'POST'])
def generate():
    """
    Run make_far on the professor's temp folder.
    Package output (PDF + Word + updated Excel files) into a zip.
    Delete temp folder after download.
    """
    folder = get_folder()
    if not folder:
        return redirect(url_for('standalone.index'))

    if request.method == 'POST':
        fmt = request.form.get('format', 'pdf')  # pdf | docx | both

        # Import generation functions from generate.py
        from app.routes.generate import (
            run_make_far, run_make_cv,
            ensure_config_updated, translate_error
        )

        make_cv_folder = os.path.join(folder, 'make_cv')
        output_files = []
        errors = []

        # Check make_cv folder exists
        if not os.path.isdir(make_cv_folder):
            flash(
                'make_cv folder not found in your uploaded folder. '
                'Please make sure your zip contains the make_cv/ subfolder.',
                'danger'
            )
            return redirect(url_for('standalone.generate'))

        # Run make_far for PDF
        if fmt in ('pdf', 'both'):
            far_folder = os.path.join(make_cv_folder, 'FAR')
            if os.path.isdir(far_folder):
                ensure_config_updated(far_folder)
                ok, err = run_make_far(far_folder, use_pandoc=False)
                if ok:
                    pdf = os.path.join(far_folder, 'far.pdf')
                    if os.path.exists(pdf):
                        output_files.append(('far.pdf', pdf))
                else:
                    current_app.logger.error(f'Standalone FAR PDF error: {err}')
                    errors.append(translate_error(err))
            else:
                errors.append('FAR/ folder not found inside make_cv/. Cannot generate PDF.')

        # Run make_far for Word
        if fmt in ('docx', 'both'):
            far_docx_folder = os.path.join(make_cv_folder, 'FAR_docx')
            if os.path.isdir(far_docx_folder):
                ensure_config_updated(far_docx_folder)
                ok, err = run_make_far(far_docx_folder, use_pandoc=True)
                if ok:
                    docx = os.path.join(far_docx_folder, 'far.docx')
                    if os.path.exists(docx):
                        output_files.append(('far.docx', docx))
                else:
                    current_app.logger.error(f'Standalone FAR docx error: {err}')
                    errors.append(translate_error(err))
            else:
                errors.append('FAR_docx/ folder not found inside make_cv/. Cannot generate Word.')

        if errors:
            for e in errors:
                flash(e, 'danger')

        if not output_files:
            return redirect(url_for('standalone.generate'))

        # Package output: FAR files + updated Excel files
        tmp_out = tempfile.mkdtemp()
        zip_name = f'FAR_Universal_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        zip_path = os.path.join(tmp_out, f'{zip_name}.zip')

        with zipfile.ZipFile(zip_path, 'w') as zf:
            # Add generated FAR/CV files
            for filename, filepath in output_files:
                zf.write(filepath, filename)

            # Add updated Excel files so professor can replace their local copies
            excel_files = [
                ('Proposals & Grants', 'grants.xlsx'),
                ('Proposals & Grants', 'proposals & grants.xlsx'),
                ('Proposals & Grants', 'expenditures.xlsx'),
                ('Awards', 'personal awards data.xlsx'),
                ('Awards', 'student awards data.xlsx'),
                ('Scholarship', 'current student data.xlsx'),
                ('Scholarship', 'thesis data.xlsx'),
                ('Service', 'service data.xlsx'),
                ('Service', 'reviews data.xlsx'),
                ('Service', 'professional development data.xlsx'),
                ('Service', 'undergraduate research data.xlsx'),
                ('Teaching', 'teaching evaluation data.xlsx'),
            ]
            for subfolder, filename in excel_files:
                src = os.path.join(folder, subfolder, filename)
                if os.path.exists(src):
                    zf.write(src, os.path.join('data', subfolder, filename))

        # Clean up temp folder
        parent = os.path.dirname(folder)
        if 'far_standalone_' in parent:
            shutil.rmtree(parent, ignore_errors=True)
        elif 'far_standalone_' in folder:
            shutil.rmtree(folder, ignore_errors=True)

        session.pop('standalone_folder', None)
        session.pop('standalone_session_id', None)

        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f'{zip_name}.zip',
            mimetype='application/zip'
        )

    return render_template('standalone/generate.html')
