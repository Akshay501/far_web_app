# app/routes/professor.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.utils import execute_query
from app.forms import PersonalAwardForm, StudentAwardForm, GrantForm, ServiceForm, ProfileForm, ProposalForm, CurrentStudentForm, ThesisForm, ReviewsForm, AdviseeCountForm, ProfessionalDevelopmentForm, ProspectiveVisitForm, UndergraduateResearchForm, AdvisingEvaluationForm
from werkzeug.utils import secure_filename
import os

professor_bp = Blueprint('professor', __name__)


def professor_required(f):
    """Decorator that enforces professor-only access."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'professor':
            flash('Professor access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ====================== DASHBOARD ======================
@professor_bp.route('/dashboard')
@login_required
@professor_required
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

    # Fetch Personal Information for the dashboard card
    try:
        professor = execute_query("""
            SELECT EmployeeID, ORCID, GoogleID, Department
            FROM PROFESSOR 
            WHERE ProfessorKey = %s
        """, (pk,), fetchone=True) or {}
    except:
        professor = {}

    return render_template('professor/dashboard.html', 
                           counts=counts, 
                           professor=professor)


# ====================== PROFILE ======================
@professor_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@professor_required
def profile():
    pk = current_user.professor_key
    form = ProfileForm()

    if form.validate_on_submit():
        execute_query("""
            UPDATE PROFESSOR 
            SET FirstName = %s,
                LastName = %s,
                ORCID = %s,
                GoogleID = %s,
                Department = %s
            WHERE ProfessorKey = %s
        """, (form.first_name.data, form.last_name.data,
              form.orcid.data, form.google_id.data,
              form.department.data, pk), commit=True)
        
        flash('Profile updated successfully', 'success')
        return redirect(url_for('professor.profile'))

    # Safe query that works even if Photo column doesn't exist yet
    try:
        professor = execute_query("""
            SELECT FirstName, LastName, ORCID, GoogleID, Department, Photo
            FROM PROFESSOR 
            WHERE ProfessorKey = %s
        """, (pk,), fetchone=True)
    except:
        # Fallback if Photo column is missing
        professor = execute_query("""
            SELECT FirstName, LastName, ORCID, GoogleID, Department
            FROM PROFESSOR 
            WHERE ProfessorKey = %s
        """, (pk,), fetchone=True)

    if professor:
        form.first_name.data = professor.get('FirstName')
        form.last_name.data = professor.get('LastName')
        form.orcid.data = professor.get('ORCID')
        form.google_id.data = professor.get('GoogleID')
        form.department.data = professor.get('Department')

    photo = professor.get('Photo') if professor and 'Photo' in professor else None

    return render_template('professor/profile.html', 
                           form=form, 
                           photo=photo)


# ====================== PROFILE UPLOAD PHOTO =================================
@professor_bp.route('/profile/upload-photo', methods=['POST'])
@login_required
@professor_required
def upload_photo():
    if 'photo' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['photo']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Correct path for your project structure (static/ is in the root folder)
    upload_folder = os.path.join(os.path.dirname(current_app.root_path), 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)

    filename = f"{current_user.professor_key}_{secure_filename(file.filename)}"
    filepath = os.path.join(upload_folder, filename)

    file.save(filepath)

    execute_query("""
        UPDATE PROFESSOR 
        SET Photo = %s 
        WHERE ProfessorKey = %s
    """, (filename, current_user.professor_key), commit=True)

    return jsonify({'success': True})


# ====================== AWARDS (Personal + Student Tabs) ======================
@professor_bp.route('/awards', methods=['GET', 'POST'])
@login_required
@professor_required
def awards():
    pk = current_user.professor_key
    
    personal_form = PersonalAwardForm()
    student_form = StudentAwardForm()

    # === Handle Personal Award submission ===
    if personal_form.validate_on_submit() and request.form.get('form_type') == 'personal':
        execute_query("""
            INSERT INTO PERSONALAWARDS (Title, AwardType, Year, ProfessorKey)
            VALUES (%s, %s, %s, %s)
        """, (personal_form.title.data, 
              personal_form.type.data,
              personal_form.year.data,
              pk), commit=True)
        flash('Personal Award added successfully', 'success')
        return redirect(url_for('professor.awards'))

    # === Handle Student Award submission (with new fields) ===
    if student_form.validate_on_submit() and request.form.get('form_type') == 'student':
        execute_query("""
            INSERT INTO STUDENTAWARDS (Student, AwardTitle, Amount, Category, Type, Year)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (student_form.student_name.data,
              student_form.award_title.data,
              student_form.amount.data,
              student_form.category.data,
              student_form.type.data,
              student_form.year.data), commit=True)
        flash('Student Award added successfully', 'success')
        return redirect(url_for('professor.awards'))

    # === Fetch data for both tabs ===
    personal_awards = execute_query("""
        SELECT pa.`Award Key`, a.Title, a.`Award Type`, a.Year, pa.Amount
        FROM PERSONALAWARDS pa
        JOIN AWARDS a ON pa.`Award Key` = a.`Award Key`
        WHERE pa.ProfessorKey = %s
        ORDER BY a.Year DESC
    """, (pk,))

    student_awards = execute_query("""
        SELECT sa.`Award Key`, a.Title, a.Year, sa.Student,
               sa.Amount, sa.Category, a.`Award Type`
        FROM STUDENTAWARDS sa
        JOIN AWARDS a ON sa.`Award Key` = a.`Award Key`
        ORDER BY a.Year DESC
    """, ())

    return render_template('professor/awards.html',
                           personal_awards=personal_awards,
                           student_awards=student_awards,
                           personal_form=personal_form,
                           student_form=student_form,
                           active_tab=request.args.get('tab', 'personal'))

# ====================== PERSONAL AWARDS EDIT/DELETE ======================
@professor_bp.route('/awards/personal/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_personal_award(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            # Title, Award Type and Year live in the AWARDS table, not PERSONALAWARDS
            execute_query("""
                UPDATE AWARDS
                SET Title=%s, `Award Type`=%s, Year=%s
                WHERE `Award Key`=%s
            """, (request.form.get('title'), request.form.get('type'),
                  request.form.get('year'), id), commit=True)
            flash('Personal Award updated successfully', 'success')
            return redirect(url_for('professor.awards'))
        form = PersonalAwardForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE PERSONALAWARDS 
                SET Title = %s, 
                    AwardType = %s, 
                    Year = %s
                WHERE `Award Key` = %s AND ProfessorKey = %s
            """, (form.title.data, 
                  form.type.data,
                  form.year.data,
                  id, pk), commit=True)
            flash('Personal Award updated successfully', 'success')
            return redirect(url_for('professor.awards'))
    else:
        award = execute_query("""
            SELECT * FROM PERSONALAWARDS 
            WHERE `Award Key` = %s AND ProfessorKey = %s
        """, (id, pk), fetchone=True)
        
        if award:
            form = PersonalAwardForm()
            form.title.data = award.get('Title')
            form.type.data = award.get('AwardType')
            form.year.data = award.get('Year')
            return render_template('professor/partials/personal_award_form.html', 
                                   form=form, id=id)

    return redirect(url_for('professor.awards'))


@professor_bp.route('/awards/personal/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_personal_award(id):
    pk = current_user.professor_key
    execute_query("DELETE FROM PERSONALAWARDS WHERE `Award Key` = %s AND ProfessorKey = %s", 
                  (id, pk), commit=True)
    flash('Personal Award deleted successfully', 'success')
    return redirect(url_for('professor.awards'))


@professor_bp.route('/awards/personal/duplicate/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_personal_award(id):
    pk = current_user.professor_key
    # Join to get Title, Award Type, Year from AWARDS table
    row = execute_query("""
        SELECT a.Title, a.`Award Type`, a.Year
        FROM PERSONALAWARDS pa
        JOIN AWARDS a ON pa.`Award Key` = a.`Award Key`
        WHERE pa.`Award Key`=%s AND pa.ProfessorKey=%s
    """, (id, pk), fetchone=True)
    if row:
        # Step 1: Insert new row into AWARDS to get a new Award Key
        execute_query(
            'INSERT INTO AWARDS (Title, Year, `Award Type`) VALUES (%s, %s, %s)',
            (row.get('Title'), row.get('Year'), row.get('Award Type')), commit=True)
        # Step 2: Get the new Award Key just created
        new_award_key = execute_query(
            'SELECT LAST_INSERT_ID() AS new_key', fetchone=True).get('new_key')
        # Step 3: Insert into PERSONALAWARDS linking to new Award Key
        execute_query(
            'INSERT INTO PERSONALAWARDS (`Award Key`, ProfessorKey) VALUES (%s, %s)',
            (new_award_key, pk), commit=True)
        flash('Personal award duplicated successfully.', 'success')
    return redirect(url_for('professor.awards'))


# ====================== STUDENT AWARDS EDIT/DELETE ======================
@professor_bp.route('/awards/student/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_student_award(id):
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            # Title, Award Type and Year live in AWARDS; Student/Amount/Category in STUDENTAWARDS
            execute_query("""
                UPDATE AWARDS
                SET Title=%s, `Award Type`=%s, Year=%s
                WHERE `Award Key`=%s
            """, (request.form.get('award_title'), request.form.get('type'),
                  request.form.get('year'), id), commit=True)
            execute_query("""
                UPDATE STUDENTAWARDS
                SET Student=%s, Amount=%s, Category=%s
                WHERE `Award Key`=%s
            """, (request.form.get('student_name'), request.form.get('amount') or None,
                  request.form.get('category'), id), commit=True)
            flash('Student Award updated successfully', 'success')
            return redirect(url_for('professor.awards', tab='student') + '#student-awards')
        form = StudentAwardForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE STUDENTAWARDS 
                SET Student = %s,
                    AwardTitle = %s,
                    Amount = %s,
                    Category = %s,
                    Type = %s,
                    Year = %s
                WHERE `Award Key` = %s
            """, (form.student_name.data,
                  form.award_title.data,
                  form.amount.data,
                  form.category.data,
                  form.type.data,
                  form.year.data,
                  id), commit=True)
            flash('Student Award updated successfully', 'success')
            return redirect(url_for('professor.awards', tab='student') + '#student-awards')
    else:
        award = execute_query("""
            SELECT * FROM STUDENTAWARDS 
            WHERE `Award Key` = %s
        """, (id,), fetchone=True)
        
        if award:
            form = StudentAwardForm()
            form.student_name.data = award.get('Student')
            form.award_title.data = award.get('AwardTitle')
            form.amount.data = award.get('Amount')
            form.category.data = award.get('Category')
            form.type.data = award.get('Type')
            form.year.data = award.get('Year')
            return render_template('professor/partials/student_award_form.html', 
                                   form=form, id=id)

    return redirect(url_for('professor.awards'))


@professor_bp.route('/awards/student/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_student_award(id):
    execute_query("DELETE FROM STUDENTAWARDS WHERE `Award Key` = %s", (id,), commit=True)
    flash('Student Award deleted successfully', 'success')
    return redirect(url_for('professor.awards'))


@professor_bp.route('/awards/student/duplicate/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_student_award(id):
    # STUDENTAWARDS stores: Award Key, Student, Amount, Category
    # Title, Award Type, Year live in AWARDS — need two-step insert
    row = execute_query("""
        SELECT a.Title, a.Year, a.`Award Type`, sa.Student, sa.Amount, sa.Category
        FROM STUDENTAWARDS sa
        JOIN AWARDS a ON sa.`Award Key` = a.`Award Key`
        WHERE sa.`Award Key`=%s
    """, (id,), fetchone=True)
    if row:
        # Step 1: Insert into AWARDS to get new Award Key
        execute_query(
            'INSERT INTO AWARDS (Title, Year, `Award Type`) VALUES (%s, %s, %s)',
            (row.get('Title'), row.get('Year'), row.get('Award Type')), commit=True)
        # Step 2: Get the new Award Key
        new_award_key = execute_query(
            'SELECT LAST_INSERT_ID() AS new_key', fetchone=True).get('new_key')
        # Step 3: Insert into STUDENTAWARDS with new Award Key
        execute_query(
            'INSERT INTO STUDENTAWARDS (`Award Key`, Student, Amount, Category) VALUES (%s, %s, %s, %s)',
            (new_award_key, row.get('Student'), row.get('Amount'), row.get('Category')), commit=True)
        flash('Student award duplicated successfully.', 'success')
    return redirect(url_for('professor.awards', tab='student') + '#student-awards')


# ====================== SERVICE (tabbed: Service, Reviews, Prof Dev, Undergrad Research) ======================
@professor_bp.route('/service', methods=['GET', 'POST'])
@login_required
@professor_required
def service():
    pk = current_user.professor_key

    service_form = ServiceForm()
    reviews_form = ReviewsForm()
    prof_dev_form = ProfessionalDevelopmentForm()
    undergrad_form = UndergraduateResearchForm()

    active_tab = request.args.get('tab', 'service')

    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type == 'service' and service_form.validate_on_submit():
            execute_query("""
                INSERT INTO SERVICE (Description, Type, Term, `Calendar Year`, `Hours/Semester`, ProfessorKey)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (service_form.description.data, service_form.type.data,
                  service_form.term.data, service_form.calendar_year.data,
                  service_form.hours.data, pk), commit=True)
            flash('Service activity added', 'success')
            return redirect(url_for('professor.service', tab='service'))

        elif form_type == 'reviews' and reviews_form.validate_on_submit():
            execute_query("""
                INSERT INTO REVIEWS (Journal, `Start Date`, Rounds, ProfessorKey)
                VALUES (%s, %s, %s, %s)
            """, (reviews_form.journal.data, reviews_form.start_date.data,
                  reviews_form.rounds.data, pk), commit=True)
            flash('Review added', 'success')
            return redirect(url_for('professor.service', tab='reviews'))

        elif form_type == 'prof_dev' and prof_dev_form.validate_on_submit():
            execute_query("""
                INSERT INTO PROFESSIONALDEVELOPMENT
                    (Description, Type, `Calendar Year`, Term, Hours, Notes, ProfessorKey)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (prof_dev_form.description.data, prof_dev_form.type.data,
                  prof_dev_form.calendar_year.data, prof_dev_form.term.data,
                  prof_dev_form.hours.data, prof_dev_form.notes.data, pk), commit=True)
            flash('Professional development entry added', 'success')
            return redirect(url_for('professor.service', tab='prof_dev'))

        elif form_type == 'undergrad' and undergrad_form.validate_on_submit():
            execute_query("""
                INSERT INTO UNDERGRADUATERESEARCH
                    (Students, Title, `Program Type`, Term, `Calendar Year`, ProfessorKey)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (undergrad_form.students.data, undergrad_form.title.data,
                  undergrad_form.program_type.data, undergrad_form.term.data,
                  undergrad_form.calendar_year.data, pk), commit=True)
            flash('Undergraduate research entry added', 'success')
            return redirect(url_for('professor.service', tab='undergrad'))

    service_data = execute_query(
        "SELECT * FROM SERVICE WHERE ProfessorKey = %s ORDER BY `Calendar Year` DESC", (pk,))
    reviews_data = execute_query(
        "SELECT * FROM REVIEWS WHERE ProfessorKey = %s ORDER BY `Start Date` DESC", (pk,))
    prof_dev_data = execute_query(
        "SELECT * FROM PROFESSIONALDEVELOPMENT WHERE ProfessorKey = %s ORDER BY `Calendar Year` DESC", (pk,))
    undergrad_data = execute_query(
        "SELECT * FROM UNDERGRADUATERESEARCH WHERE ProfessorKey = %s ORDER BY `Calendar Year` DESC", (pk,))

    return render_template('professor/service.html',
        service_form=service_form, reviews_form=reviews_form,
        prof_dev_form=prof_dev_form, undergrad_form=undergrad_form,
        service_data=service_data, reviews_data=reviews_data,
        prof_dev_data=prof_dev_data, undergrad_data=undergrad_data,
        active_tab=active_tab)


# ====================== TEACHING & EXPENDITURE (Read-only, filtered by professor) ======================
@professor_bp.route('/teaching')
@login_required
@professor_required
def teaching():
    pk = current_user.professor_key
    data = execute_query(
        "SELECT * FROM TEACHINGEVALUATION WHERE ProfessorKey = %s ORDER BY EvaluationYear DESC, Term",
        (pk,)
    )
    return render_template('professor/teaching.html', data=data)


@professor_bp.route('/expenditure')
@login_required
@professor_required
def expenditure():
    pk = current_user.professor_key
    data = execute_query(
        "SELECT * FROM EXPENDITURE WHERE ProfessorKey = %s ORDER BY Year DESC",
        (pk,)
    )
    return render_template('professor/expenditure.html', data=data)


# ====================== PROPOSALS ======================
@professor_bp.route('/proposals', methods=['GET', 'POST'])
@login_required
@professor_required
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
@professor_required
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


# ====================== PROPOSALS EDIT/DELETE ======================
@professor_bp.route('/proposals/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_proposal(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            execute_query("""
                UPDATE PROPOSAL
                SET Title=%s, Sponsor=%s, `Allocated Amount`=%s, `Total Cost`=%s,
                    `Funded?`=%s, `Begin Date`=%s, `End Date`=%s,
                    `Submit Date`=%s, `Principal Investigator`=%s
                WHERE `Proposal Key`=%s AND ProfessorKey=%s
            """, (request.form.get('title'), request.form.get('sponsor'),
                  request.form.get('allocated_amount') or None,
                  request.form.get('total_cost') or None,
                  1 if request.form.get('funded') in ('1', 'Y', True) else 0,
                  request.form.get('begin_date') or None,
                  request.form.get('end_date') or None,
                  request.form.get('submit_date') or None,
                  request.form.get('principal_investigators'), id, pk), commit=True)
            flash('Proposal updated successfully', 'success')
            return redirect(url_for('professor.proposals'))
        form = ProposalForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE PROPOSAL
                SET Title=%s, Sponsor=%s, `Allocated Amount`=%s, `Total Cost`=%s,
                    `Funded?`=%s, `Begin Date`=%s, `End Date`=%s,
                    `Submit Date`=%s, `Principal Investigator`=%s
                WHERE `Proposal Key`=%s AND ProfessorKey=%s
            """, (form.title.data, form.sponsor.data, form.allocated_amount.data,
                  form.total_cost.data, form.funded.data, form.begin_date.data,
                  form.end_date.data, form.submit_date.data,
                  form.principal_investigators.data, id, pk), commit=True)
            flash('Proposal updated successfully', 'success')
            return redirect(url_for('professor.proposals'))
    else:
        proposal = execute_query(
            "SELECT * FROM PROPOSAL WHERE `Proposal Key`=%s AND ProfessorKey=%s",
            (id, pk), fetchone=True)
        if proposal:
            form = ProposalForm()
            form.title.data = proposal.get('Title')
            form.sponsor.data = proposal.get('Sponsor')
            form.allocated_amount.data = proposal.get('AllocatedAmount')
            form.total_cost.data = proposal.get('TotalCost')
            form.funded.data = proposal.get('Funded?')
            form.begin_date.data = proposal.get('Begin Date')
            form.end_date.data = proposal.get('End Date')
            form.submit_date.data = proposal.get('Submit Date')
            form.principal_investigators.data = proposal.get('Principal Investigator')
            return render_template('professor/partials/proposal_form.html', form=form, id=id)
    return redirect(url_for('professor.proposals'))


@professor_bp.route('/proposals/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_proposal(id):
    pk = current_user.professor_key
    execute_query(
        "DELETE FROM PROPOSAL WHERE `Proposal Key`=%s AND ProfessorKey=%s",
        (id, pk), commit=True)
    flash('Proposal deleted successfully', 'success')
    return redirect(url_for('professor.proposals'))


@professor_bp.route('/proposals/duplicate/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_proposal(id):
    pk = current_user.professor_key
    row = execute_query(
        'SELECT * FROM PROPOSAL WHERE `Proposal Key`=%s AND ProfessorKey=%s',
        (id, pk), fetchone=True)
    if row:
        execute_query(
            'INSERT INTO PROPOSAL (Title, Sponsor, `Allocated Amount`, `Total Cost`, `Funded?`, `Begin Date`, `End Date`, `Submit Date`, `Principal Investigator`, ProfessorKey) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (row.get('Title'), row.get('Sponsor'), row.get('Allocated Amount'), row.get('Total Cost'),
             row.get('Funded?'), row.get('Begin Date'), row.get('End Date'),
             row.get('Submit Date'), row.get('Principal Investigator'), pk), commit=True)
        flash('Proposal duplicated successfully.', 'success')
    return redirect(url_for('professor.proposals'))


# ====================== SERVICE EDIT/DELETE ======================
@professor_bp.route('/service/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_service(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            execute_query("""
                UPDATE SERVICE
                SET Description=%s, Type=%s, Term=%s,
                    `Calendar Year`=%s, `Hours/Semester`=%s
                WHERE `Service Key`=%s AND ProfessorKey=%s
            """, (request.form.get('description'), request.form.get('type'),
                  request.form.get('term'), request.form.get('calendar_year') or None,
                  request.form.get('hours') or None, id, pk), commit=True)
            flash('Service updated successfully', 'success')
            return redirect(url_for('professor.service', tab='service'))
        form = ServiceForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE SERVICE
                SET Description=%s, Type=%s, Term=%s,
                    `Calendar Year`=%s, `Hours/Semester`=%s
                WHERE `Service Key`=%s AND ProfessorKey=%s
            """, (form.description.data, form.type.data, form.term.data,
                  form.calendar_year.data, form.hours.data, id, pk), commit=True)
            flash('Service updated successfully', 'success')
            return redirect(url_for('professor.service', tab='service'))
    else:
        row = execute_query(
            "SELECT * FROM SERVICE WHERE `Service Key`=%s AND ProfessorKey=%s",
            (id, pk), fetchone=True)
        if row:
            form = ServiceForm()
            form.description.data = row.get('Description')
            form.type.data = row.get('Type')
            form.term.data = row.get('Term')
            form.calendar_year.data = row.get('Calendar Year')
            form.hours.data = row.get('Hours/Semester')
            return render_template('professor/partials/service_form.html', form=form, id=id)
    return redirect(url_for('professor.service', tab='service'))


@professor_bp.route('/service/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_service(id):
    pk = current_user.professor_key
    execute_query(
        "DELETE FROM SERVICE WHERE `Service Key`=%s AND ProfessorKey=%s",
        (id, pk), commit=True)
    flash('Service deleted successfully', 'success')
    return redirect(url_for('professor.service', tab='service'))


@professor_bp.route('/service/duplicate/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_service(id):
    pk = current_user.professor_key
    row = execute_query(
        "SELECT * FROM SERVICE WHERE `Service Key`=%s AND ProfessorKey=%s",
        (id, pk), fetchone=True)
    if row:
        execute_query("""
            INSERT INTO SERVICE (Description, Type, Term, `Calendar Year`, `Hours/Semester`, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (row.get('Description'), row.get('Type'), row.get('Term'),
              row.get('Calendar Year'), row.get('Hours/Semester'), pk), commit=True)
        flash('Service activity duplicated successfully.', 'success')
    return redirect(url_for('professor.service', tab='service'))


@professor_bp.route('/grants/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_grant(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            execute_query("""
                UPDATE GRANTS
                SET Title=%s, Sponsor=%s, `Allocated Amount`=%s, `Total Cost`=%s,
                    `Begin Date`=%s, `End Date`=%s, Role=%s, `Principal Investigators`=%s
                WHERE GrantKey=%s AND ProfessorKey=%s
            """, (request.form.get('title'), request.form.get('sponsor'),
                  request.form.get('allocated_amount') or None,
                  request.form.get('total_cost') or None,
                  request.form.get('begin_date') or None,
                  request.form.get('end_date') or None,
                  request.form.get('role'),
                  request.form.get('principal_investigators'), id, pk), commit=True)
            flash('Grant updated successfully', 'success')
            return redirect(url_for('professor.grants'))
        form = GrantForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE GRANTS
                SET Title=%s, Sponsor=%s, `Allocated Amount`=%s, `Total Cost`=%s,
                    `Begin Date`=%s, `End Date`=%s, Role=%s, `Principal Investigators`=%s
                WHERE GrantKey=%s AND ProfessorKey=%s
            """, (form.title.data, form.sponsor.data, form.allocated_amount.data,
                  form.total_cost.data, form.begin_date.data,
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
@professor_required
def delete_grant(id):
    pk = current_user.professor_key
    execute_query("DELETE FROM GRANTS WHERE GrantKey=%s AND ProfessorKey=%s", (id, pk), commit=True)
    flash('Grant deleted successfully', 'success')
    return redirect(url_for('professor.grants'))


@professor_bp.route('/grants/duplicate/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_grant(id):
    pk = current_user.professor_key
    row = execute_query(
        'SELECT * FROM GRANTS WHERE GrantKey=%s AND ProfessorKey=%s',
        (id, pk), fetchone=True)
    if row:
        execute_query(
            'INSERT INTO GRANTS (Title, Sponsor, `Allocated Amount`, `Total Cost`, `Begin Date`, `End Date`, Role, `Principal Investigators`, ProfessorKey) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (row.get('Title'), row.get('Sponsor'), row.get('Allocated Amount'), row.get('Total Cost'),
             row.get('Begin Date'), row.get('End Date'), row.get('Role'),
             row.get('Principal Investigators'), pk), commit=True)
        flash('Grant duplicated successfully.', 'success')
    return redirect(url_for('professor.grants'))


# ====================== CV ======================
@professor_bp.route('/generate_cv')
@login_required
@professor_required
def generate_cv_route():
    from app.utils import generate_cv
    pdf_path = generate_cv(current_user.professor_key)
    if pdf_path:
        return send_file(pdf_path, as_attachment=True)
    flash('CV generation failed', 'danger')
    return redirect(url_for('professor.dashboard'))


# ====================== SCHOLARSHIP (Two Tabs with Full CRUD) ======================
@professor_bp.route('/scholarship', methods=['GET', 'POST'])
@login_required
@professor_required
def scholarship():
    pk = current_user.professor_key

    current_student_form = CurrentStudentForm()
    thesis_form = ThesisForm()

    # === Add Current Student ===
    if current_student_form.validate_on_submit() and request.form.get('form_type') == 'current_student':
        execute_query("""
            INSERT INTO CURRENTSTUDENTS (`Student Name`, `Current Program`, `Start Date`, ProfessorKey)
            VALUES (%s, %s, %s, %s)
        """, (current_student_form.student_name.data,
              current_student_form.current_program.data,
              current_student_form.start_date.data,
              pk), commit=True)
        flash('Current student added successfully', 'success')
        return redirect(url_for('professor.scholarship'))

    # === Add Thesis ===
    if thesis_form.validate_on_submit() and request.form.get('form_type') == 'thesis':
        execute_query("""
            INSERT INTO THESIS (Student, Year, Degree, Title, Comments, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (thesis_form.student.data,
              thesis_form.year.data,
              thesis_form.degree.data,
              thesis_form.title.data,
              thesis_form.comments.data,
              pk), commit=True)
        flash('Thesis added successfully', 'success')
        return redirect(url_for('professor.scholarship'))

    # Load data for both tabs
    current_students = execute_query("""
        SELECT `Student Key`,
               `Student Name`,
               `Current Program`,
               `Start Date`
        FROM CURRENTSTUDENTS 
        WHERE ProfessorKey = %s
    """, (pk,))

    theses = execute_query("""
        SELECT * FROM THESIS WHERE ProfessorKey = %s
    """, (pk,))

    return render_template('professor/scholarship.html',
                           current_students=current_students,
                           theses=theses,
                           current_student_form=current_student_form,
                           thesis_form=thesis_form)


# ====================== SCHOLARSHIP ADD ROUTES ======================
@professor_bp.route('/scholarship/add/current_student', methods=['GET'])
@login_required
@professor_required
def add_current_student_form():
    form = CurrentStudentForm()
    return render_template('professor/partials/current_student_form.html', form=form)


@professor_bp.route('/scholarship/add/thesis', methods=['GET'])
@login_required
@professor_required
def add_thesis_form():
    form = ThesisForm()
    return render_template('professor/partials/thesis_form.html', form=form)


# ====================== SCHOLARSHIP EDIT ROUTES ======================
@professor_bp.route('/scholarship/edit/current_student/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_current_student(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            execute_query("""
                UPDATE CURRENTSTUDENTS
                SET `Student Name`=%s, `Current Program`=%s, `Start Date`=%s
                WHERE ProfessorKey=%s AND `Student Key`=%s
            """, (request.form.get('student_name'),
                  request.form.get('current_program'),
                  request.form.get('start_date') or None, pk, id), commit=True)
            flash('Student updated successfully', 'success')
            return redirect(url_for('professor.scholarship'))
        form = CurrentStudentForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE CURRENTSTUDENTS 
                SET `Student Name` = %s, `Current Program` = %s, `Start Date` = %s
                WHERE ProfessorKey = %s AND `Student Key` = %s
            """, (form.student_name.data, form.current_program.data, form.start_date.data, pk, id), commit=True)
            flash('Current student updated successfully', 'success')
            return redirect(url_for('professor.scholarship'))
    else:
        row = execute_query("""
            SELECT * FROM CURRENTSTUDENTS 
            WHERE ProfessorKey = %s AND `Student Key` = %s
        """, (pk, id), fetchone=True)
        if row:
            form = CurrentStudentForm()
            form.student_name.data = row.get('Student Name')
            form.current_program.data = row.get('Current Program')
            form.start_date.data = row.get('Start Date')
            return render_template('professor/partials/current_student_form.html', form=form, id=id)
    return redirect(url_for('professor.scholarship'))


@professor_bp.route('/scholarship/edit/thesis/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_thesis(id):
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            execute_query("""
                UPDATE THESIS
                SET `Student Name`=%s, Year=%s, Degree=%s, Title=%s, Comments=%s
                WHERE ProfessorKey=%s AND `Thesis Key`=%s
            """, (request.form.get('student'), request.form.get('year') or None,
                  request.form.get('degree'), request.form.get('title'),
                  request.form.get('comments'),
                  current_user.professor_key, id), commit=True)
            flash('Thesis updated successfully', 'success')
            return redirect(url_for('professor.scholarship') + '?tab=thesis')
        form = ThesisForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE THESIS 
                SET `Student Name` = %s, Year = %s, Degree = %s, Title = %s, Comments = %s
                WHERE ProfessorKey = %s AND `Thesis Key` = %s
            """, (form.student.data, form.year.data, form.degree.data, 
                  form.title.data, form.comments.data, current_user.professor_key, id), commit=True)
            flash('Thesis updated successfully', 'success')
            return redirect(url_for('professor.scholarship'))
    else:
        row = execute_query("""
            SELECT * FROM THESIS 
            WHERE ProfessorKey = %s AND `Thesis Key` = %s
        """, (current_user.professor_key, id), fetchone=True)
        if row:
            form = ThesisForm()
            form.student.data = row.get('Student Name')
            form.year.data = row.get('Year')
            form.degree.data = row.get('Degree')
            form.title.data = row.get('Title')
            form.comments.data = row.get('Comments')
            return render_template('professor/partials/thesis_form.html', form=form, id=id)
    return redirect(url_for('professor.scholarship'))


# ====================== SCHOLARSHIP DELETE ROUTES ======================
@professor_bp.route('/scholarship/delete/current_student/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_current_student(id):
    pk = current_user.professor_key
    execute_query("DELETE FROM CURRENTSTUDENTS WHERE ProfessorKey = %s AND `Student Key` = %s", 
                  (pk, id), commit=True)
    flash('Current student deleted successfully', 'success')
    return redirect(url_for('professor.scholarship'))


@professor_bp.route('/scholarship/duplicate/current_student/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_current_student(id):
    pk = current_user.professor_key
    row = execute_query(
        'SELECT * FROM CURRENTSTUDENTS WHERE ProfessorKey=%s AND `Student Key`=%s',
        (pk, id), fetchone=True)
    if row:
        execute_query(
            'INSERT INTO CURRENTSTUDENTS (`Student Name`, `Current Program`, `Start Date`, ProfessorKey) VALUES (%s, %s, %s, %s)',
            (row.get('Student Name'), row.get('Current Program'), row.get('Start Date'), pk), commit=True)
        flash('Student duplicated successfully.', 'success')
    return redirect(url_for('professor.scholarship'))


@professor_bp.route('/scholarship/delete/thesis/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_thesis(id):
    pk = current_user.professor_key
    execute_query("DELETE FROM THESIS WHERE ProfessorKey = %s AND `Thesis Key` = %s", 
                  (pk, id), commit=True)
    flash('Thesis deleted successfully', 'success')
    return redirect(url_for('professor.scholarship'))


@professor_bp.route('/scholarship/duplicate/thesis/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_thesis(id):
    pk = current_user.professor_key
    row = execute_query(
        'SELECT * FROM THESIS WHERE ProfessorKey=%s AND `Thesis Key`=%s',
        (pk, id), fetchone=True)
    if row:
        execute_query(
            'INSERT INTO THESIS (`Student Name`, Year, Degree, Title, Comments, ProfessorKey) VALUES (%s, %s, %s, %s, %s, %s)',
            (row.get('Student Name'), row.get('Year'), row.get('Degree'),
             row.get('Title'), row.get('Comments'), pk), commit=True)
        flash('Thesis duplicated successfully.', 'success')
    return redirect(url_for('professor.scholarship') + '?tab=thesis')

# ====================== REVIEWS ======================
@professor_bp.route('/reviews', methods=['GET', 'POST'])
@login_required
@professor_required
def reviews():
    pk = current_user.professor_key
    form = ReviewsForm()
    if form.validate_on_submit():
        execute_query("""
            INSERT INTO REVIEWS (Journal, `Start Date`, Rounds, ProfessorKey)
            VALUES (%s, %s, %s, %s)
        """, (form.journal.data, form.start_date.data, form.rounds.data, pk), commit=True)
        flash('Review added successfully', 'success')
        return redirect(url_for('professor.service', tab='reviews'))
    data = execute_query(
        "SELECT * FROM REVIEWS WHERE ProfessorKey = %s ORDER BY `Start Date` DESC", (pk,))
    return render_template('professor/reviews.html', form=form, data=data)


@professor_bp.route('/reviews/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_review(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            execute_query("""
                UPDATE REVIEWS SET Journal=%s, `Start Date`=%s, Rounds=%s
                WHERE `Reviews Key`=%s AND ProfessorKey=%s
            """, (request.form.get('journal'),
                  request.form.get('start_date') or None,
                  request.form.get('rounds') or None, id, pk), commit=True)
            flash('Review updated successfully', 'success')
            return redirect(url_for('professor.service', tab='reviews'))
        form = ReviewsForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE REVIEWS SET Journal=%s, `Start Date`=%s, Rounds=%s
                WHERE `Reviews Key`=%s AND ProfessorKey=%s
            """, (form.journal.data, form.start_date.data, form.rounds.data, id, pk), commit=True)
            flash('Review updated successfully', 'success')
            return redirect(url_for('professor.service', tab='reviews'))
    else:
        row = execute_query(
            "SELECT * FROM REVIEWS WHERE `Reviews Key`=%s AND ProfessorKey=%s",
            (id, pk), fetchone=True)
        if row:
            form = ReviewsForm()
            form.journal.data = row.get('Journal') or ''
            form.start_date.data = row.get('Start Date') or None
            form.rounds.data = row.get('Rounds') or 1
            return render_template('professor/partials/reviews_form.html', form=form, id=id)
    return redirect(url_for('professor.service', tab='reviews'))


@professor_bp.route('/reviews/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_review(id):
    pk = current_user.professor_key
    execute_query(
        "DELETE FROM REVIEWS WHERE `Reviews Key`=%s AND ProfessorKey=%s",
        (id, pk), commit=True)
    flash('Review deleted successfully', 'success')
    return redirect(url_for('professor.service', tab='reviews'))


@professor_bp.route('/reviews/duplicate/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_review(id):
    pk = current_user.professor_key
    row = execute_query(
        "SELECT * FROM REVIEWS WHERE `Reviews Key`=%s AND ProfessorKey=%s",
        (id, pk), fetchone=True)
    if row:
        execute_query("""
            INSERT INTO REVIEWS (Journal, `Start Date`, Rounds, ProfessorKey)
            VALUES (%s, %s, %s, %s)
        """, (row.get('Journal'), row.get('Start Date'), row.get('Rounds'), pk), commit=True)
        flash('Review duplicated successfully.', 'success')
    return redirect(url_for('professor.service', tab='reviews'))


# ====================== ADVISEE COUNT ======================
# READ-ONLY — data imported from university system (PeopleSoft)
@professor_bp.route('/advisee-count', methods=['GET'])
@login_required
@professor_required
def advisee_count():
    pk = current_user.professor_key
    data = execute_query(
        "SELECT * FROM ADVISEECOUNT WHERE ProfessorKey = %s ORDER BY Year DESC, Term", (pk,))
    return render_template('professor/advisee_count.html', data=data)


@professor_bp.route('/advisee-count/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_advisee_count(id):
    # READ-ONLY — block all edit attempts
    flash('Advisee count data is read-only and cannot be edited.', 'warning')
    return redirect(url_for('professor.advisee_count'))


@professor_bp.route('/advisee-count/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_advisee_count(id):
    # READ-ONLY — block all delete attempts
    flash('Advisee count data is read-only and cannot be deleted.', 'warning')
    return redirect(url_for('professor.advisee_count'))


# ====================== PROFESSIONAL DEVELOPMENT ======================
@professor_bp.route('/professional-development', methods=['GET', 'POST'])
@login_required
@professor_required
def professional_development():
    pk = current_user.professor_key
    form = ProfessionalDevelopmentForm()
    if form.validate_on_submit():
        execute_query("""
            INSERT INTO PROFESSIONALDEVELOPMENT
                (Description, Type, `Calendar Year`, Term, Hours, Notes, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (form.description.data, form.type.data, form.calendar_year.data,
              form.term.data, form.hours.data, form.notes.data, pk), commit=True)
        flash('Professional development entry added', 'success')
        return redirect(url_for('professor.service', tab='prof_dev'))
    data = execute_query("""
        SELECT * FROM PROFESSIONALDEVELOPMENT
        WHERE ProfessorKey = %s ORDER BY `Calendar Year` DESC, Term
    """, (pk,))
    return render_template('professor/professional_development.html', form=form, data=data)


@professor_bp.route('/professional-development/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_professional_development(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            execute_query("""
                UPDATE PROFESSIONALDEVELOPMENT
                SET Description=%s, Type=%s, Term=%s, `Calendar Year`=%s, Hours=%s
                WHERE `Professional Development Key`=%s AND ProfessorKey=%s
            """, (request.form.get('description'), request.form.get('type'),
                  request.form.get('term'),
                  request.form.get('calendar_year') or None,
                  request.form.get('hours') or None, id, pk), commit=True)
            flash('Entry updated successfully', 'success')
            return redirect(url_for('professor.service', tab='prof_dev'))
        form = ProfessionalDevelopmentForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE PROFESSIONALDEVELOPMENT
                SET Description=%s, Type=%s, `Calendar Year`=%s, Term=%s, Hours=%s, Notes=%s
                WHERE `Professional Development Key`=%s AND ProfessorKey=%s
            """, (form.description.data, form.type.data, form.calendar_year.data,
                  form.term.data, form.hours.data, form.notes.data, id, pk), commit=True)
            flash('Entry updated', 'success')
            return redirect(url_for('professor.service', tab='prof_dev'))
    else:
        row = execute_query("""
            SELECT * FROM PROFESSIONALDEVELOPMENT
            WHERE `Professional Development Key`=%s AND ProfessorKey=%s
        """, (id, pk), fetchone=True)
        if row:
            form = ProfessionalDevelopmentForm()
            form.description.data = row.get('Description') or ''
            form.type.data = row.get('Type') or 'Conference'
            form.calendar_year.data = row.get('Calendar Year') or 2025
            form.term.data = row.get('Term') or 'Fall'
            form.hours.data = row.get('Hours') or 0
            form.notes.data = row.get('Notes') or ''
            return render_template('professor/partials/professional_development_form.html', form=form, id=id)
    return redirect(url_for('professor.service', tab='prof_dev'))


@professor_bp.route('/professional-development/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_professional_development(id):
    pk = current_user.professor_key
    execute_query("""
        DELETE FROM PROFESSIONALDEVELOPMENT
        WHERE `Professional Development Key`=%s AND ProfessorKey=%s
    """, (id, pk), commit=True)
    flash('Entry deleted', 'success')
    return redirect(url_for('professor.service', tab='prof_dev'))


@professor_bp.route('/professional-development/duplicate/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_professional_development(id):
    pk = current_user.professor_key
    row = execute_query("""
        SELECT * FROM PROFESSIONALDEVELOPMENT
        WHERE `Professional Development Key`=%s AND ProfessorKey=%s
    """, (id, pk), fetchone=True)
    if row:
        execute_query("""
            INSERT INTO PROFESSIONALDEVELOPMENT
            (Description, Type, `Calendar Year`, Notes, Term, Hours, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (row.get('Description'), row.get('Type'), row.get('Calendar Year'),
              row.get('Notes'), row.get('Term'), row.get('Hours'), pk), commit=True)
        flash('Entry duplicated successfully.', 'success')
    return redirect(url_for('professor.service', tab='prof_dev'))


# ====================== PROSPECTIVE VISIT ======================
@professor_bp.route('/prospective-visit', methods=['GET', 'POST'])
@login_required
@professor_required
def prospective_visit():
    pk = current_user.professor_key
    form = ProspectiveVisitForm()
    if form.validate_on_submit():
        execute_query("""
            INSERT INTO PROSPECTIVEVISIT (Staff, Year, Visits, Deposits, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s)
        """, (form.staff.data, form.year.data, form.visits.data,
              form.deposits.data, pk), commit=True)
        flash('Prospective visit added', 'success')
        return redirect(url_for('professor.prospective_visit'))
    data = execute_query(
        "SELECT * FROM PROSPECTIVEVISIT WHERE ProfessorKey = %s ORDER BY Year DESC", (pk,))
    return render_template('professor/prospective_visit.html', form=form, data=data)


@professor_bp.route('/prospective-visit/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_prospective_visit(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        form = ProspectiveVisitForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE PROSPECTIVEVISIT
                SET Staff=%s, Year=%s, Visits=%s, Deposits=%s
                WHERE `Prospective Visit Key`=%s AND ProfessorKey=%s
            """, (form.staff.data, form.year.data, form.visits.data,
                  form.deposits.data, id, pk), commit=True)
            flash('Visit updated', 'success')
            return redirect(url_for('professor.prospective_visit'))
    else:
        row = execute_query("""
            SELECT * FROM PROSPECTIVEVISIT
            WHERE `Prospective Visit Key`=%s AND ProfessorKey=%s
        """, (id, pk), fetchone=True)
        if row:
            form = ProspectiveVisitForm()
            form.staff.data = row.get('Staff') or ''
            form.year.data = row.get('Year') or 2025
            form.visits.data = row.get('Visits') or 0
            form.deposits.data = row.get('Deposits') or 0
            return render_template('professor/partials/prospective_visit_form.html', form=form, id=id)
    return redirect(url_for('professor.prospective_visit'))


@professor_bp.route('/prospective-visit/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_prospective_visit(id):
    pk = current_user.professor_key
    execute_query("""
        DELETE FROM PROSPECTIVEVISIT
        WHERE `Prospective Visit Key`=%s AND ProfessorKey=%s
    """, (id, pk), commit=True)
    flash('Visit deleted', 'success')
    return redirect(url_for('professor.prospective_visit'))


# ====================== UNDERGRADUATE RESEARCH ======================
@professor_bp.route('/undergraduate-research', methods=['GET', 'POST'])
@login_required
@professor_required
def undergraduate_research():
    pk = current_user.professor_key
    form = UndergraduateResearchForm()
    if form.validate_on_submit():
        execute_query("""
            INSERT INTO UNDERGRADUATERESEARCH
                (Students, Title, `Program Type`, Term, `Calendar Year`, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (form.students.data, form.title.data, form.program_type.data,
              form.term.data, form.calendar_year.data, pk), commit=True)
        flash('Undergraduate research entry added', 'success')
        return redirect(url_for('professor.service', tab='undergrad'))
    data = execute_query("""
        SELECT * FROM UNDERGRADUATERESEARCH
        WHERE ProfessorKey = %s ORDER BY `Calendar Year` DESC
    """, (pk,))
    return render_template('professor/undergraduate_research.html', form=form, data=data)


@professor_bp.route('/undergraduate-research/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@professor_required
def edit_undergraduate_research(id):
    pk = current_user.professor_key
    if request.method == 'POST':
        if request.form.get('inline_edit'):
            execute_query("""
                UPDATE UNDERGRADUATERESEARCH
                SET Students=%s, Title=%s, `Program Type`=%s, Term=%s, `Calendar Year`=%s
                WHERE `Undergraduate Research Key`=%s AND ProfessorKey=%s
            """, (request.form.get('students'), request.form.get('title'),
                  request.form.get('program_type'), request.form.get('term'),
                  request.form.get('calendar_year') or None, id, pk), commit=True)
            flash('Entry updated successfully', 'success')
            return redirect(url_for('professor.service', tab='undergrad'))
        form = UndergraduateResearchForm()
        if form.validate_on_submit():
            execute_query("""
                UPDATE UNDERGRADUATERESEARCH
                SET Students=%s, Title=%s, `Program Type`=%s, Term=%s, `Calendar Year`=%s
                WHERE `Undergraduate Research Key`=%s AND ProfessorKey=%s
            """, (form.students.data, form.title.data, form.program_type.data,
                  form.term.data, form.calendar_year.data, id, pk), commit=True)
            flash('Entry updated', 'success')
            return redirect(url_for('professor.service', tab='undergrad'))
    else:
        row = execute_query("""
            SELECT * FROM UNDERGRADUATERESEARCH
            WHERE `Undergraduate Research Key`=%s AND ProfessorKey=%s
        """, (id, pk), fetchone=True)
        if row:
            form = UndergraduateResearchForm()
            form.students.data = row.get('Students') or ''
            form.title.data = row.get('Title') or ''
            form.program_type.data = row.get('Program Type') or 'Summer REU Program'
            form.term.data = row.get('Term') or 'Fall'
            form.calendar_year.data = row.get('Calendar Year') or 2025
            return render_template('professor/partials/undergraduate_research_form.html', form=form, id=id)
    return redirect(url_for('professor.service', tab='undergrad'))


@professor_bp.route('/undergraduate-research/delete/<int:id>', methods=['POST'])
@login_required
@professor_required
def delete_undergraduate_research(id):
    pk = current_user.professor_key
    execute_query("""
        DELETE FROM UNDERGRADUATERESEARCH
        WHERE `Undergraduate Research Key`=%s AND ProfessorKey=%s
    """, (id, pk), commit=True)
    flash('Entry deleted', 'success')
    return redirect(url_for('professor.service', tab='undergrad'))


@professor_bp.route('/undergraduate-research/duplicate/<int:id>', methods=['POST'])
@login_required
@professor_required
def duplicate_undergraduate_research(id):
    pk = current_user.professor_key
    row = execute_query("""
        SELECT * FROM UNDERGRADUATERESEARCH
        WHERE `Undergraduate Research Key`=%s AND ProfessorKey=%s
    """, (id, pk), fetchone=True)
    if row:
        execute_query("""
            INSERT INTO UNDERGRADUATERESEARCH
            (Students, Title, `Program Type`, Term, `Calendar Year`, ProfessorKey)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (row.get('Students'), row.get('Title'), row.get('Program Type'),
              row.get('Term'), row.get('Calendar Year'), pk), commit=True)
        flash('Entry duplicated successfully.', 'success')
    return redirect(url_for('professor.service', tab='undergrad'))


# ====================== ADVISING EVALUATION (Read-only) ======================
@professor_bp.route('/advising-evaluation')
@login_required
@professor_required
def advising_evaluation():
    pk = current_user.professor_key
    data = execute_query("""
        SELECT * FROM ADVISINGEVALUATION
        WHERE ProfessorKey = %s ORDER BY EvaluationYear DESC, Term
    """, (pk,))
    return render_template('professor/advising_evaluation.html', data=data)
