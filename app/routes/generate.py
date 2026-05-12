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

from app.utils import execute_query
from app.excel_export import export_all

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


def get_professor_folder(professor_key):
    """
    Returns the path to the professor's data folder.
    Format: <departments_root>/<Department>/<LastName, FirstName>
    """
    prof = execute_query(
        "SELECT FirstName, LastName, Department FROM PROFESSOR WHERE ProfessorKey = %s",
        (professor_key,), fetchone=True
    )
    if not prof:
        return None, None

    departments_root = current_app.config.get('DEPARTMENTS_ROOT', '')
    folder_name = f"{prof['LastName']}, {prof['FirstName']}"
    department = prof.get('Department', '')
    professor_folder = os.path.join(departments_root, department, folder_name)
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

    # Student awards: join STUDENTAWARDS with AWARDS via PERSONALAWARDS to filter by professor
    student_awards = q("""
        SELECT a.Title, a.Year, a.`Award Type`, sa.Student, sa.Amount, sa.Category
        FROM STUDENTAWARDS sa
        JOIN AWARDS a ON sa.`Award Key` = a.`Award Key`
        JOIN PERSONALAWARDS pa ON pa.`Award Key` = a.`Award Key`
        WHERE pa.ProfessorKey = %s
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


def run_make_far(far_folder, use_pandoc=False):
    """
    Call make_far from within the FAR or FAR_docx folder.
    Returns (success, error_message)
    """
    import sys
    try:
        from make_cv.make_far import main as make_far_main
        original_dir = os.getcwd()
        original_argv = sys.argv
        os.chdir(far_folder)
        try:
            # Replace sys.argv so argparse does not pick up Flask arguments
            argv = ['-p'] if use_pandoc else []
            sys.argv = ['make_far'] + argv
            make_far_main(argv)
        finally:
            os.chdir(original_dir)
            sys.argv = original_argv
        return True, None
    except Exception as e:
        return False, str(e)


def run_make_cv(cv_folder):
    """
    Call make_cv from within the CV folder.
    Returns (success, error_message)
    """
    import sys
    try:
        from make_cv.make_cv import main as make_cv_main
        original_dir = os.getcwd()
        original_argv = sys.argv
        os.chdir(cv_folder)
        try:
            sys.argv = ['make_cv']
            make_cv_main([])
        finally:
            os.chdir(original_dir)
            sys.argv = original_argv
        return True, None
    except Exception as e:
        return False, str(e)


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

        pk = current_user.professor_key
        professor_folder, prof = get_professor_folder(pk)

        if not professor_folder:
            flash('Professor profile not found.', 'danger')
            return redirect(url_for('generate.generate'))

        if not os.path.isdir(professor_folder):
            flash(f'Data folder not found: {professor_folder}. Please contact the administrator.', 'danger')
            return redirect(url_for('generate.generate'))

        # Save uploaded .bib file into Scholarship/
        if bib_file and bib_file.filename.endswith('.bib'):
            bib_path = os.path.join(professor_folder, 'Scholarship', 'scholarship.bib')
            os.makedirs(os.path.dirname(bib_path), exist_ok=True)
            bib_file.save(bib_path)

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
                ok, err = run_make_far(far_folder, use_pandoc=False)
                if ok:
                    pdf = os.path.join(far_folder, 'far.pdf')
                    if os.path.exists(pdf):
                        output_files.append(('far.pdf', pdf))
                else:
                    errors.append(f'FAR PDF error: {err}')

            if fmt in ('docx', 'both'):
                far_docx_folder = os.path.join(make_cv_folder, 'FAR_docx')
                ok, err = run_make_far(far_docx_folder, use_pandoc=True)
                if ok:
                    docx = os.path.join(far_docx_folder, 'far.docx')
                    if os.path.exists(docx):
                        output_files.append(('far.docx', docx))
                else:
                    errors.append(f'FAR docx error: {err}')

        if doc_type in ('cv', 'both'):
            cv_folder = os.path.join(make_cv_folder, 'CV')
            ok, err = run_make_cv(cv_folder)
            if ok:
                pdf = os.path.join(cv_folder, 'cv.pdf')
                if os.path.exists(pdf):
                    output_files.append(('cv.pdf', pdf))
            else:
                errors.append(f'CV error: {err}')

        if errors:
            for e in errors:
                flash(e, 'danger')

        if not output_files:
            flash('No output files were generated. Check that LaTeX and pandoc are installed.', 'danger')
            return redirect(url_for('generate.generate'))

        # Package output into a zip and send
        tmp_dir  = tempfile.mkdtemp()
        zip_name = f"FAR_{prof['LastName']}_{datetime.now().strftime('%Y%m%d')}"
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

        tmp_dir  = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_dir, 'all_fars.zip')
        results  = []

        import zipfile
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for prof in professors:
                pk     = prof['ProfessorKey']
                name   = f"{prof['LastName']}, {prof['FirstName']}"
                dept   = prof.get('Department', '')
                departments_root = current_app.config.get('DEPARTMENTS_ROOT', '')
                professor_folder = os.path.join(departments_root, dept, name)

                if not os.path.isdir(professor_folder):
                    results.append({'name': name, 'status': '❌ folder not found'})
                    continue

                try:
                    db_data = fetch_all_db_data(pk)
                    export_all(pk, professor_folder, db_data)
                except Exception as e:
                    results.append({'name': name, 'status': f'❌ export error: {e}'})
                    continue

                make_cv_folder = os.path.join(professor_folder, 'make_cv')

                if fmt in ('pdf', 'both'):
                    far_folder = os.path.join(make_cv_folder, 'FAR')
                    ok, err = run_make_far(far_folder, use_pandoc=False)
                    if ok:
                        pdf = os.path.join(far_folder, 'far.pdf')
                        if os.path.exists(pdf):
                            zf.write(pdf, f"{name}/far.pdf")
                            results.append({'name': name, 'status': '✅ PDF generated'})
                    else:
                        results.append({'name': name, 'status': f'❌ {err}'})

                if fmt in ('docx', 'both'):
                    far_docx = os.path.join(make_cv_folder, 'FAR_docx')
                    ok, err = run_make_far(far_docx, use_pandoc=True)
                    if ok:
                        docx = os.path.join(far_docx, 'far.docx')
                        if os.path.exists(docx):
                            zf.write(docx, f"{name}/far.docx")

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
