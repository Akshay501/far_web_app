# app/routes/professor.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.utils import execute_query
from app.forms import AwardForm, GrantForm, ServiceForm, ProfileForm, ProposalForm

professor_bp = Blueprint('professor', __name__)

# ====================== DASHBOARD ======================
@professor_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'professor':
        return redirect(url_for('auth.login'))
    
    pk = current_user.professor_key

    # Safe counting with try/except because not all tables have ProfessorKey
    counts = {
        'awards': 0,
        'grants': 0,
        'students': 0,
        'theses': 0,
    }

    try:
        counts['awards'] = len(execute_query("SELECT 1 FROM AWARDS WHERE ProfessorKey = %s", (pk,)))
    except:
        pass

    try:
        counts['grants'] = len(execute_query("SELECT 1 FROM GRANTS WHERE ProfessorKey = %s", (pk,)))
    except:
        pass

    try:
        counts['students'] = len(execute_query("SELECT 1 FROM CURRENTSTUDENTS WHERE ProfessorKey = %s", (pk,)))
    except:
        pass

    try:
        counts['theses'] = len(execute_query("SELECT 1 FROM THESIS WHERE ProfessorKey = %s", (pk,)))
    except:
        pass

    return render_template('professor/dashboard.html', counts=counts)


# ====================== PROFILE ======================
@professor_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    pk = current_user.professor_key
    form = ProfileForm()
    if form.validate_on_submit():
        execute_query("""
            UPDATE PROFESSOR 
            SET FirstName=%s, LastName=%s, ORCID=%s, GoogleID=%s, Department=%s 
            WHERE ProfessorKey=%s
        """, (form.first_name.data, form.last_name.data, form.orcid.data,
              form.google_id.data, form.department.data, pk), commit=True)
        flash('Profile updated successfully', 'success')
        return redirect(url_for('professor.profile'))

    professor = execute_query("SELECT * FROM PROFESSOR WHERE ProfessorKey = %s", (pk,), fetchone=True)
    if professor:
        form.first_name.data = professor.get('FirstName')
        form.last_name.data = professor.get('LastName')
        form.orcid.data = professor.get('ORCID')
        form.google_id.data = professor.get('GoogleID')
        form.department.data = professor.get('Department')

    return render_template('professor/profile.html', professor=professor, form=form)


# ====================== AWARDS ======================
@professor_bp.route('/awards', methods=['GET', 'POST'])
@login_required
def awards():
    pk = current_user.professor_key
    form = AwardForm()
    if form.validate_on_submit():
        execute_query(
            "INSERT INTO AWARDS (Title, Year, AwardType) VALUES (%s, %s, %s)",
            (form.title.data, form.year.data, form.award_type.data), commit=True)
        flash('Award added successfully', 'success')
        return redirect(url_for('professor.awards'))

    data = execute_query("SELECT * FROM AWARDS ORDER BY Year DESC")
    return render_template('professor/awards.html', data=data, form=form)


@professor_bp.route('/awards/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_award(id):
    if request.method == 'POST':
        form = AwardForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE AWARDS SET Title=%s, Year=%s, AwardType=%s 
                WHERE AwardKey=%s
            """, (form.title.data, form.year.data, form.award_type.data, id), commit=True)
            flash('Award updated', 'success')
            return redirect(url_for('professor.awards'))
    else:
        award = execute_query("SELECT * FROM AWARDS WHERE AwardKey=%s", (id,), fetchone=True)
        if award:
            form = AwardForm()
            form.title.data = award['Title']
            form.year.data = award['Year']
            form.award_type.data = award.get('AwardType')
            return render_template('professor/partials/award_form.html', form=form, id=id, type='award')
    return redirect(url_for('professor.awards'))


@professor_bp.route('/awards/delete/<int:id>', methods=['POST'])
@login_required
def delete_award(id):
    execute_query("DELETE FROM AWARDS WHERE AwardKey=%s", (id,), commit=True)
    flash('Award deleted', 'success')
    return redirect(url_for('professor.awards'))

# ====================== SERVICE ======================
@professor_bp.route('/service', methods=['GET', 'POST'])
@login_required
def service():
    pk = current_user.professor_key
    form = ServiceForm()
    if form.validate_on_submit():
        execute_query("""
            INSERT INTO SERVICE (Description, Type, Term, CalendarYear, HoursSemester, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (form.description.data, form.type.data, form.term.data,
              form.calendar_year.data, form.hours.data, pk), commit=True)
        flash('Service activity added', 'success')
        return redirect(url_for('professor.service'))
    data = execute_query("SELECT * FROM SERVICE WHERE ProfessorKey = %s", (pk,))
    return render_template('professor/service.html', data=data, form=form)


# ====================== TEACHING & EXPENDITURE (Read-only) ======================
@professor_bp.route('/teaching')
@login_required
def teaching():
    data = execute_query("SELECT * FROM TEACHINGEVALUATION")
    return render_template('professor/teaching.html', data=data)


@professor_bp.route('/expenditure')
@login_required
def expenditure():
    data = execute_query("SELECT * FROM EXPENDITURE")
    return render_template('professor/expenditure.html', data=data)


# ====================== PROPOSALS ======================
@professor_bp.route('/proposals', methods=['GET', 'POST'])
@login_required
def proposals():
    pk = current_user.professor_key
    form = ProposalForm()
    if form.validate_on_submit():
        execute_query("""
            INSERT INTO PROPOSAL (Title, Sponsor, AllocatedAmount, TotalCost, Funded, 
            BeginDate, EndDate, SubmitDate, PrincipalInvestigators, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (form.title.data, form.sponsor.data, form.allocated_amount.data,
              form.total_cost.data, form.funded.data, form.begin_date.data,
              form.end_date.data, form.submit_date.data, 
              form.principal_investigators.data, pk), commit=True)
        flash('Proposal added successfully', 'success')
        return redirect(url_for('professor.proposals'))

    data = execute_query("SELECT * FROM PROPOSAL WHERE ProfessorKey = %s", (pk,))
    return render_template('professor/proposals.html', data=data, form=form)


# ====================== GRANTS ======================
@professor_bp.route('/grants', methods=['GET', 'POST'])
@login_required
def grants():
    pk = current_user.professor_key
    form = GrantForm()
    if form.validate_on_submit():
        execute_query("""
            INSERT INTO GRANTS (Title, Sponsor, AllocatedAmount, TotalCost, Funded, 
            BeginDate, EndDate, Role, PrincipalInvestigators, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (form.title.data, form.sponsor.data, form.allocated_amount.data,
              form.total_cost.data, form.funded.data, form.begin_date.data,
              form.end_date.data, form.role.data, form.principal_investigators.data, 
              pk), commit=True)
        flash('Grant added successfully', 'success')
        return redirect(url_for('professor.grants'))

    data = execute_query("SELECT * FROM GRANTS WHERE ProfessorKey = %s", (pk,))
    return render_template('professor/grants.html', data=data, form=form)


@professor_bp.route('/grants/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_grant(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        form = GrantForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE GRANTS 
                SET Title=%s, Sponsor=%s, AllocatedAmount=%s, TotalCost=%s, Funded=%s,
                    BeginDate=%s, EndDate=%s, Role=%s, PrincipalInvestigators=%s
                WHERE GrantKey=%s AND ProfessorKey=%s
            """, (form.title.data, form.sponsor.data, form.allocated_amount.data,
                  form.total_cost.data, form.funded.data, form.begin_date.data,
                  form.end_date.data, form.role.data, form.principal_investigators.data,
                  id, pk), commit=True)
            flash('Grant updated successfully', 'success')
            return redirect(url_for('professor.grants'))
    else:
        grant = execute_query("SELECT * FROM GRANTS WHERE GrantKey=%s AND ProfessorKey=%s", 
                            (id, pk), fetchone=True)
        if grant:
            form = GrantForm()
            form.title.data = grant.get('Title')
            form.sponsor.data = grant.get('Sponsor')
            form.allocated_amount.data = grant.get('AllocatedAmount')
            form.total_cost.data = grant.get('TotalCost')
            form.funded.data = grant.get('Funded')
            form.begin_date.data = grant.get('BeginDate')
            form.end_date.data = grant.get('EndDate')
            form.role.data = grant.get('Role')
            form.principal_investigators.data = grant.get('PrincipalInvestigators')
            return render_template('professor/partials/grant_form.html', form=form, id=id, type='grant')
    return redirect(url_for('professor.grants'))


@professor_bp.route('/grants/delete/<int:id>', methods=['POST'])
@login_required
def delete_grant(id):
    pk = current_user.professor_key
    execute_query("DELETE FROM GRANTS WHERE GrantKey=%s AND ProfessorKey=%s", (id, pk), commit=True)
    flash('Grant deleted successfully', 'success')
    return redirect(url_for('professor.grants'))

# ====================== CV ======================
@professor_bp.route('/generate_cv')
@login_required
def generate_cv_route():
    from app.utils import generate_cv
    pdf_path = generate_cv(current_user.professor_key)
    if pdf_path:
        return send_file(pdf_path, as_attachment=True)
    flash('CV generation failed', 'danger')
    return redirect(url_for('professor.dashboard'))

# ====================== SCHOLARSHIP ======================
@professor_bp.route('/scholarship')
@login_required
def scholarship():
    pk = current_user.professor_key
    
    current_students = execute_query(
        "SELECT * FROM CURRENTSTUDENTS WHERE ProfessorKey = %s", (pk,))
    
    theses = execute_query(
        "SELECT * FROM THESIS WHERE ProfessorKey = %s", (pk,))
    
    undergrad_research = execute_query(
        "SELECT * FROM UNDERGRADUATERESEARCH WHERE ProfessorKey = %s", (pk,))
    
    return render_template('professor/scholarship.html',
                           current_students=current_students,
                           theses=theses,
                           undergrad_research=undergrad_research)