from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DateField, SelectField, DecimalField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional

class AwardForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    year = IntegerField('Year', validators=[Optional()])
    award_type = SelectField('Type', choices=[('Teaching', 'Teaching'), ('Research', 'Research'), ('Service', 'Service'), ('Mentoring', 'Mentoring')])
    submit = SubmitField('Save Award')

class GrantForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    sponsor = StringField('Sponsor')
    allocated_amount = DecimalField('Allocated Amount')
    total_cost = DecimalField('Total Cost')
    begin_date = DateField('Begin Date', format='%Y-%m-%d')
    end_date = DateField('End Date', format='%Y-%m-%d')
    submit = SubmitField('Save Grant')

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

# Add more forms as needed for other tables (ThesisForm, ServiceForm, etc.)
# For brevity, we implement full CRUD for main tables; pattern is identical.