from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import check_password_hash, generate_password_hash
from app.utils import execute_query
from app.models import User
from app.forms import RegistrationForm
from app.folder_service import ensure_professor_folder, FolderCreationError

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user_data = execute_query(
            "SELECT * FROM users WHERE Email = %s",
            (form.email.data,),
            fetchone=True
        )
        if user_data and check_password_hash(user_data['Password'], form.password.data):
            user = User(user_data)
            login_user(user)
            flash('Login successful', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('professor.dashboard'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html', form=form)

@auth_bp.route('/logout')
def logout():
    logout_user()                   
    session.clear()                 
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Professor self-signup. Accounts activate immediately; the on-disk
    folder is created afterwards and its failure is deliberately
    non-blocking (retried at first generation)."""
    form = RegistrationForm()
    form.department.choices = [
        (d, d) for d in current_app.config.get('DEPARTMENTS', [])]

    if form.validate_on_submit():
        email = form.email.data.strip().lower()

        existing = execute_query(
            'SELECT UserID FROM users WHERE Email = %s',
            (email,), fetchone=True)
        if existing:
            flash('An account with that email already exists. '
                  'Try signing in instead.', 'danger')
            return render_template('register.html', form=form)

        first = form.first_name.data.strip()
        last = form.last_name.data.strip()
        middle = (form.middle_name.data or '').strip() or None
        google_id = (form.google_id.data or '').strip() or None
        orcid = (form.orcid.data or '').strip() or None
        scopus_id = (form.scopus_id.data or '').strip() or None

        # 1) The account — committed first. It must exist regardless of
        #    what happens to the folder below.
        professor_key = execute_query(
            'INSERT INTO PROFESSOR '
            '(FirstName, MiddleName, LastName, Department, GoogleID, ORCID, ScopusID) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (first, middle, last, form.department.data,
             google_id, orcid, scopus_id),
            commit=True, lastrowid=True)
        execute_query(
            'INSERT INTO users (Name, Email, Password, Role, ProfessorKey) '
            'VALUES (%s, %s, %s, %s, %s)',
            (f'{first} {last}', email,
             generate_password_hash(form.password.data),
             'professor', professor_key),
            commit=True)

        # 2) The folder — decoupled. Failure is logged and surfaced as a
        #    non-blocking notice; creation is retried at first generation.
        try:
            ensure_professor_folder(
                professor_key, first, last, email,
                google_id=google_id, orcid=orcid, scopus_id=scopus_id)
        except FolderCreationError as exc:
            current_app.logger.warning(
                'Folder creation failed for professor %s: %s',
                professor_key, exc)
            flash('Your account was created. Your data folder could not '
                  'be set up yet; it will be created automatically when '
                  'you first generate a report.', 'warning')
        else:
            flash('Account created. Please sign in.', 'success')

        return redirect(url_for('auth.login'))

    return render_template('register.html', form=form)