# app/routes/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.utils import execute_query
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
