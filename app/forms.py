from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DateField, SelectField, DecimalField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional

class PersonalAwardForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    type = SelectField('Type', choices=[
        ('Professional', 'Professional'),
        ('School', 'School'),
        ('Department', 'Department'),
        ('University', 'University')
    ], validators=[DataRequired()])
    year = IntegerField('Year', validators=[DataRequired()])
    submit = SubmitField('Save Personal Award')

class StudentAwardForm(FlaskForm):
    student_name = StringField('Student', validators=[DataRequired()])
    award_title = StringField('Title', validators=[DataRequired()])
    amount = DecimalField('Amount', places=2)
    category = SelectField('Category', choices=[
        ('Conference', 'Conference'),
        ('Fellowship', 'Fellowship'),
        ('Travel', 'Travel'),
        ('Research', 'Research')
    ])
    type = SelectField('Type', choices=[
        ('Undergraduate', 'Undergraduate'),
        ('Graduate', 'Graduate')
    ])
    year = IntegerField('Year', validators=[DataRequired()])
    submit = SubmitField('Save Student Award')

class ServiceForm(FlaskForm):
    description = StringField('Description', validators=[DataRequired()])
    type = SelectField('Type', choices=[('Department', 'Department'), ('University', 'University'), ('Professional', 'Professional'), ('Community', 'Community')])
    term = SelectField('Term', choices=[('Fall', 'Fall'), ('Spring', 'Spring'), ('Summer', 'Summer'), ('Full Year', 'Full Year')])
    calendar_year = IntegerField('Calendar Year')
    hours = DecimalField('Hours/Semester', places=2)
    submit = SubmitField('Save Service')

class ProfileForm(FlaskForm):
    first_name = StringField('First Name')
    last_name = StringField('Last Name')
    orcid = StringField('ORCID')
    google_id = StringField('Google Scholar ID')
    department = StringField('Department')
    submit = SubmitField('Update Profile')

class ProposalForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    sponsor = StringField('Sponsor')
    allocated_amount = DecimalField('Allocated Amount', places=2)
    total_cost = DecimalField('Total Cost', places=2)
    funded = SelectField('Funded?', choices=[('Y', 'Yes'), ('N', 'No')])
    begin_date = DateField('Begin Date', format='%Y-%m-%d')
    end_date = DateField('End Date', format='%Y-%m-%d')
    submit_date = DateField('Submit Date', format='%Y-%m-%d')
    principal_investigators = TextAreaField('Principal Investigators')
    submit = SubmitField('Save Proposal')

class GrantForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    sponsor = StringField('Sponsor')
    allocated_amount = DecimalField('Allocated Amount', places=2)
    total_cost = DecimalField('Total Cost', places=2)
    funded = SelectField('Funded?', choices=[('Y', 'Yes'), ('N', 'No')])
    begin_date = DateField('Begin Date', format='%Y-%m-%d')
    end_date = DateField('End Date', format='%Y-%m-%d')
    role = SelectField('Role', choices=[('PI', 'Principal Investigator'), ('Co-PI', 'Co-Principal Investigator')])
    principal_investigators = TextAreaField('Principal Investigators')
    submit = SubmitField('Save Grant')


class CurrentStudentForm(FlaskForm):
    student_name = StringField('Student Name', validators=[DataRequired()])
    current_program = SelectField('Current Program', choices=[('MS', 'MS'), ('PhD', 'PhD'), ('ME', 'ME')], validators=[DataRequired()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Save')

class ThesisForm(FlaskForm):
    student = StringField('Student Name', validators=[DataRequired()])
    year = IntegerField('Year', validators=[DataRequired()])
    degree = SelectField('Degree', choices=[('MS', 'MS'), ('PhD', 'PhD'), ('ME', 'ME')], validators=[DataRequired()])
    title = StringField('Title', validators=[DataRequired()])
    comments = TextAreaField('Comments')
    submit = SubmitField('Save')

# Add more forms as needed for other tables (ThesisForm, ServiceForm, etc.)
# For brevity, we implement full CRUD for main tables; pattern is identical.

class ReviewsForm(FlaskForm):
    journal = StringField('Journal / Conference', validators=[DataRequired()])
    start_date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    rounds = IntegerField('Rounds', validators=[Optional()])
    submit = SubmitField('Save Review')


class AdviseeCountForm(FlaskForm):
    advisor_name = StringField('Advisor Name', validators=[DataRequired()])
    advisee_count = IntegerField('Advisee Count', validators=[DataRequired()])
    year = IntegerField('Year', validators=[DataRequired()])
    term = SelectField('Term', choices=[
        ('Fall', 'Fall'), ('Spring', 'Spring'),
        ('Summer', 'Summer'), ('Full Year', 'Full Year')
    ])
    submit = SubmitField('Save Advisee Count')


class ProfessionalDevelopmentForm(FlaskForm):
    description = TextAreaField('Description', validators=[DataRequired()])
    type = SelectField('Type', choices=[
        ('Conference', 'Conference'),
        ('Workshop', 'Workshop'),
        ('Online Certification', 'Online Certification'),
        ('Training/Workshop Leader', 'Training/Workshop Leader'),
        ('Leadership Program', 'Leadership Program'),
        ('Other', 'Other'),
    ])
    calendar_year = IntegerField('Calendar Year', validators=[DataRequired()])
    term = SelectField('Term', choices=[
        ('Fall', 'Fall'), ('Spring', 'Spring'),
        ('Summer', 'Summer'), ('Full Year', 'Full Year')
    ])
    hours = DecimalField('Hours', places=2, validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Entry')


class ProspectiveVisitForm(FlaskForm):
    staff = TextAreaField('Staff / Description', validators=[DataRequired()])
    year = IntegerField('Year', validators=[DataRequired()])
    visits = IntegerField('Number of Visits', validators=[Optional()])
    deposits = DecimalField('Deposits ($)', places=2, validators=[Optional()])
    submit = SubmitField('Save Visit')


class UndergraduateResearchForm(FlaskForm):
    students = TextAreaField('Students', validators=[DataRequired()])
    title = StringField('Project Title', validators=[DataRequired()])
    program_type = SelectField('Program Type', choices=[
        ('Summer REU Program', 'Summer REU Program'),
        ('Honors Thesis', 'Honors Thesis'),
        ('Independent Study', 'Independent Study'),
        ('Capstone Project', 'Capstone Project'),
        ('Undergraduate Research Assistantship', 'Undergraduate Research Assistantship'),
        ('Other', 'Other'),
    ])
    term = SelectField('Term', choices=[
        ('Fall', 'Fall'), ('Spring', 'Spring'),
        ('Summer', 'Summer'), ('Full Year', 'Full Year')
    ])
    calendar_year = IntegerField('Calendar Year', validators=[DataRequired()])
    submit = SubmitField('Save Research')


class AdvisingEvaluationForm(FlaskForm):
    evaluation_id = StringField('Evaluation ID', validators=[Optional()])
    name = StringField('Name', validators=[Optional()])
    term = SelectField('Term', choices=[
        ('Fall', 'Fall'), ('Spring', 'Spring'),
        ('Summer', 'Summer'), ('Full Year', 'Full Year')
    ])
    evaluation_year = IntegerField('Year', validators=[Optional()])
    average_pct = DecimalField('Average PCT', places=2, validators=[Optional()])
    submit = SubmitField('Save Evaluation')
