# app/routes/admin.py
import secrets

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app.utils import execute_query
from app.forms import AdminCreateProfessorForm
from app.accounts import create_professor_account, DuplicateEmailError, ensure_folder_for_existing
from functools import wraps

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    """Decorator that enforces admin-only access on any route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ====================== DASHBOARD ======================
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    professors = execute_query("""
        SELECT
            p.ProfessorKey,
            p.FirstName,
            p.LastName,
            p.Department,
            u.Email,
            (SELECT COUNT(*) FROM GRANTS            WHERE ProfessorKey = p.ProfessorKey) AS grant_count,
            (SELECT COUNT(*) FROM THESIS             WHERE ProfessorKey = p.ProfessorKey) AS thesis_count,
            (SELECT COUNT(*) FROM SERVICE            WHERE ProfessorKey = p.ProfessorKey) AS service_count,
            (SELECT COUNT(*) FROM TEACHINGEVALUATION WHERE ProfessorKey = p.ProfessorKey) AS teaching_count,
            (SELECT COUNT(*) FROM PROPOSAL          WHERE ProfessorKey = p.ProfessorKey) AS proposal_count,
            (SELECT COUNT(*) FROM PERSONALAWARDS    WHERE ProfessorKey = p.ProfessorKey) AS award_count,
            (SELECT COUNT(*) FROM EXPENDITURE       WHERE ProfessorKey = p.ProfessorKey) AS expenditure_count
        FROM PROFESSOR p
        LEFT JOIN users u ON u.ProfessorKey = p.ProfessorKey
        ORDER BY p.LastName
    """)
    return render_template('admin/dashboard.html', professors=professors)


# ====================== VIEW PROFESSOR FAR ======================
@admin_bp.route('/professor/<int:pk>')
@login_required
@admin_required
def view_professor(pk):
    professor = execute_query(
        "SELECT * FROM PROFESSOR WHERE ProfessorKey = %s", (pk,), fetchone=True
    )
    if not professor:
        flash('Professor not found.', 'danger')
        return redirect(url_for('admin.dashboard'))

    data = {
        'grants':    execute_query("SELECT * FROM GRANTS WHERE ProfessorKey = %s ORDER BY `Begin Date` DESC", (pk,)),
        'proposals': execute_query("SELECT * FROM PROPOSAL WHERE ProfessorKey = %s ORDER BY `Begin Date` DESC", (pk,)),
        'thesis':    execute_query("SELECT * FROM THESIS WHERE ProfessorKey = %s ORDER BY Year DESC", (pk,)),
        'service':   execute_query("SELECT * FROM SERVICE WHERE ProfessorKey = %s ORDER BY `Calendar Year` DESC", (pk,)),
        'teaching':  execute_query("SELECT * FROM TEACHINGEVALUATION WHERE ProfessorKey = %s ORDER BY EvaluationYear DESC", (pk,)),
        'expenditure': execute_query("SELECT * FROM EXPENDITURE WHERE ProfessorKey = %s ORDER BY Year DESC", (pk,)),
        'awards':    execute_query("""
                        SELECT pa.Amount, a.Title, a.Year, a.`Award Type`
                        FROM PERSONALAWARDS pa
                        JOIN AWARDS a ON a.`Award Key` = pa.`Award Key`
                        WHERE pa.ProfessorKey = %s ORDER BY a.Year DESC
                     """, (pk,)),
    }

    return render_template('admin/view_professor.html', professor=professor, data=data)


# ====================== ADD PROFESSOR ======================
@admin_bp.route('/professor/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_professor():
    """Admin creates a professor account. Same rules as self-registration
    (shared creation logic, same email-domain restriction and department
    list); the password is generated server-side and shown once."""
    form = AdminCreateProfessorForm()
    form.department.choices = [
        (d, d) for d in current_app.config.get('DEPARTMENTS', [])]

    if form.validate_on_submit():
        temp_password = secrets.token_urlsafe(9)
        try:
            professor_key, folder_error = create_professor_account(
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                password=temp_password,
                department=form.department.data,
                middle_name=form.middle_name.data,
                google_id=form.google_id.data,
                orcid=form.orcid.data,
                scopus_id=form.scopus_id.data)
        except DuplicateEmailError:
            flash('An account with that email already exists.', 'danger')
            return render_template('admin/add_professor.html', form=form)

        flash(f'Professor account created. Temporary password: '
              f'{temp_password} — share it securely; it is shown only '
              f'this once.', 'success')
        if folder_error:
            flash('The data folder could not be set up yet; it will be '
                  'created automatically at first report generation.',
                  'warning')
        return redirect(url_for('admin.view_professor', pk=professor_key))

    return render_template('admin/add_professor.html', form=form)


# ====================== CREATE / REPAIR FOLDER ======================
@admin_bp.route('/professor/<int:pk>/create-folder', methods=['POST'])
@login_required
@admin_required
def create_professor_folder(pk):
    """On-demand folder healing for one professor, from their view page."""
    status, error = ensure_folder_for_existing(pk)
    if error:
        flash(f'Folder could not be created: {error}', 'danger')
    elif status == 'exists':
        flash('The data folder already exists — nothing to repair.', 'info')
    else:
        flash('Data folder created.', 'success')
    return redirect(url_for('admin.view_professor', pk=pk))
