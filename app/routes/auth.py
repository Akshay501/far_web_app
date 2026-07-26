from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import check_password_hash, generate_password_hash
from app.utils import execute_query
from app.models import User
from app.forms import RegistrationForm, ChangePasswordForm
from app.accounts import create_professor_account, DuplicateEmailError

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
        try:
            professor_key, folder_error = create_professor_account(
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                password=form.password.data,
                department=form.department.data,
                middle_name=form.middle_name.data,
                google_id=form.google_id.data,
                orcid=form.orcid.data,
                scopus_id=form.scopus_id.data)
        except DuplicateEmailError:
            flash('An account with that email already exists. '
                  'Try signing in instead.', 'danger')
            return render_template('register.html', form=form)

        if folder_error:
            flash('Your account was created. Your data folder could not '
                  'be set up yet; it will be created automatically when '
                  'you first generate a report.', 'warning')
        else:
            flash('Account created. Please sign in.', 'success')

        return redirect(url_for('auth.login'))

    return render_template('register.html', form=form)

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change your own password. Available to professors AND admins —
    the admin account ships with a default password and had no way to
    replace it. On success the session is dropped and the user signs in
    again, which is the honest way to make the change take effect
    everywhere without stale-session bookkeeping."""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        row = execute_query('SELECT Password FROM users WHERE UserID = %s',
                            (current_user.id,), fetchone=True)
        if not row or not check_password_hash(row['Password'],
                                              form.current_password.data):
            flash('Your current password is not correct.', 'danger')
            return render_template('change_password.html', form=form)

        execute_query(
            'UPDATE users SET Password = %s WHERE UserID = %s',
            (generate_password_hash(form.new_password.data),
             current_user.id), commit=True)
        current_app.logger.info('Password changed for user %s',
                                current_user.id)
        logout_user()
        session.clear()
        flash('Password changed. Please sign in with your new password.',
              'success')
        return redirect(url_for('auth.login'))

    return render_template('change_password.html', form=form)
