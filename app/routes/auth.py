from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, session, current_app, abort)
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import check_password_hash, generate_password_hash
from app.utils import execute_query
from app.models import User
from app.forms import RegistrationForm, ChangePasswordForm
from app.accounts import create_professor_account, DuplicateEmailError
from app.cas import (login_url, logout_url, validate_ticket,
                     CASError, CASUnavailable)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

def _cas_server():
    """The CAS server address, or None when CAS is switched off."""
    return current_app.config.get('CAS_SERVER_URL')


def _callback_url():
    # Built the same way for the login redirect and for validation:
    # CAS refuses a ticket whose service URL differs by even a slash.
    return url_for('auth.cas_callback', _external=True)


def _dashboard_for(user):
    if user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('professor.dashboard'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if _cas_server():
        # CAS on: nobody signs in with a password here. A POST is not
        # processed at all (no back door around CAS); the emergency
        # admin password lives at /admin-login.
        if request.method == 'POST':
            return redirect(url_for('auth.login'))
        return redirect(login_url(_cas_server(), _callback_url()))

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

def _cas_error(status, title, message):
    return render_template('cas_error.html', title=title,
                           message=message), status


@auth_bp.route('/cas/callback')
def cas_callback():
    """Where CAS sends the browser back, with ?ticket=ST-...

    The NetID is taken ONLY from CAS's server-to-server answer. Anything
    else in the query string is ignored. Every refusal happens before
    the database is touched, except the NetID lookup itself."""
    cas = _cas_server()
    if not cas:
        abort(404)

    ticket = request.args.get('ticket')
    if not ticket:
        return _cas_error(
            400, 'Sign-in did not complete',
            'Clarkson did not send back a sign-in ticket. Please try '
            'signing in again.')

    try:
        netid, _attributes = validate_ticket(cas, ticket, _callback_url())
    except CASUnavailable as exc:
        current_app.logger.warning('CAS unavailable during login: %s', exc)
        return _cas_error(
            503, 'Clarkson sign-in is unavailable',
            'The Clarkson sign-in service could not be reached. Please '
            'try again in a few minutes.')
    except CASError as exc:
        current_app.logger.warning('CAS ticket rejected: %s', exc)
        return _cas_error(
            403, 'Sign-in could not be confirmed',
            'Clarkson could not confirm this sign-in. It may have '
            'expired — please try signing in again.')

    user_data = execute_query('SELECT * FROM users WHERE NetID = %s',
                              (netid,), fetchone=True)
    if not user_data:
        # Admin-created accounts only (Brian, 2026-10-10): a valid
        # Clarkson login with no FAR account is turned away, and
        # nothing is created.
        current_app.logger.info('CAS login refused: no account for %s',
                                netid)
        return _cas_error(
            403, 'No FAR account',
            f'You signed in to Clarkson as "{netid}", but there is no '
            f'Faculty Activity Report account for that NetID. Please '
            f'contact your department administrator.')

    session.clear()             # no session fixation: start fresh
    user = User(user_data)
    login_user(user)
    flash('Login successful', 'success')
    return _dashboard_for(user)


@auth_bp.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    """Emergency password login, for ADMIN accounts only — so the
    system can still be run if Clarkson's CAS is down. Professors
    always sign in through CAS once it is switched on."""
    form = LoginForm()
    if form.validate_on_submit():
        user_data = execute_query('SELECT * FROM users WHERE Email = %s',
                                  (form.email.data,), fetchone=True)
        if (user_data and user_data.get('Role') == 'admin'
                and check_password_hash(user_data['Password'],
                                        form.password.data)):
            session.clear()
            user = User(user_data)
            login_user(user)
            current_app.logger.info('Emergency admin login: user %s',
                                    user.id)
            flash('Login successful', 'success')
            return _dashboard_for(user)
        # Same message whether the email exists, isn't an admin, or the
        # password is wrong: nothing to learn by probing.
        flash('Invalid administrator email or password', 'danger')
    return render_template('login.html', form=form, emergency=True)


@auth_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    cas = _cas_server()
    if cas:
        # End the Clarkson session too; otherwise "Log in" would let the
        # same person straight back in without a password.
        return redirect(logout_url(cas, url_for('auth.login',
                                                _external=True)))
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Professor self-signup. Accounts activate immediately; the on-disk
    folder is created afterwards and its failure is deliberately
    non-blocking (retried at first generation).

    Closed while CAS is on: accounts are created by an administrator."""
    if _cas_server():
        flash('Accounts are created by your department administrator.',
              'info')
        return redirect(url_for('auth.login'))
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
    if _cas_server() and current_user.role != 'admin':
        # Under CAS a professor has no password here to change: they
        # sign in with their Clarkson account. Only the admin's
        # emergency password remains.
        flash('You sign in with your Clarkson account, so there is no '
              'separate password to change here.', 'info')
        return redirect(url_for('professor.dashboard'))

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
