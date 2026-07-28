"""
Shared professor account creation.

Used by both self-registration (/register) and the admin add-professor
path, so the sequence is defined exactly once:

  1. refuse duplicate emails
  2. INSERT the PROFESSOR row (lastrowid -> the new ProfessorKey)
  3. INSERT the linked users row (password hashed here)
     -- both committed: the account exists from this point on --
  4. attempt folder creation, decoupled: a failure is logged and
     reported back to the caller, but never undoes the account
     (creation is retried at first generation)
"""
import os

from flask import current_app
from werkzeug.security import generate_password_hash

from app.utils import execute_query
from app.folder_service import (ensure_professor_folder, FolderCreationError,
                                render_contactinfo, write_personal_data,
                                contactinfo_is_app_owned)


class DuplicateEmailError(Exception):
    """An account with this email already exists."""


def create_professor_account(*, first_name, last_name, email, password,
                             department, middle_name=None, google_id=None,
                             orcid=None, scopus_id=None):
    """
    Create a professor account and attempt its on-disk folder.

    Returns (professor_key, folder_error): folder_error is None when the
    folder was created, else the error message (the account still exists).
    Raises DuplicateEmailError if the email is already registered.
    """
    email = email.strip().lower()
    first = first_name.strip()
    last = last_name.strip()
    middle = (middle_name or '').strip() or None
    google_id = (google_id or '').strip() or None
    orcid = (orcid or '').strip() or None
    scopus_id = (scopus_id or '').strip() or None

    existing = execute_query(
        'SELECT UserID FROM users WHERE Email = %s',
        (email,), fetchone=True)
    if existing:
        raise DuplicateEmailError(email)

    professor_key = execute_query(
        'INSERT INTO PROFESSOR '
        '(FirstName, MiddleName, LastName, Department, GoogleID, ORCID, ScopusID) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (first, middle, last, department, google_id, orcid, scopus_id),
        commit=True, lastrowid=True)
    execute_query(
        'INSERT INTO users (Name, Email, Password, Role, ProfessorKey) '
        'VALUES (%s, %s, %s, %s, %s)',
        (f'{first} {last}', email, generate_password_hash(password),
         'professor', professor_key),
        commit=True)

    folder_error = None
    try:
        ensure_professor_folder(
            professor_key, first, last, email,
            google_id=google_id, orcid=orcid, scopus_id=scopus_id)
    except FolderCreationError as exc:
        current_app.logger.warning(
            'Folder creation failed for professor %s: %s',
            professor_key, exc)
        folder_error = str(exc)

    return professor_key, folder_error


def ensure_folder_for_existing(professor_key):
    """
    Make sure an EXISTING professor's folder is on disk, gathering their
    identity from the database. This is the self-healing entry point:
    called at generation time (so a folder that failed at registration
    gets built on first use) and by the admin repair action.

    Returns (status, error): ('created' | 'exists', None) on success,
    (None, message) on failure. Never raises.
    """
    prof = execute_query(
        'SELECT FirstName, LastName, GoogleID, ORCID, ScopusID '
        'FROM PROFESSOR WHERE ProfessorKey = %s',
        (professor_key,), fetchone=True)
    if not prof:
        return None, f'Professor {professor_key} not found.'

    user = execute_query(
        'SELECT Email FROM users WHERE ProfessorKey = %s',
        (professor_key,), fetchone=True)
    email = (user or {}).get('Email') or ''

    try:
        status = ensure_professor_folder(
            professor_key,
            prof.get('FirstName') or '',
            prof.get('LastName') or '',
            email,
            google_id=prof.get('GoogleID'),
            orcid=prof.get('ORCID'),
            scopus_id=prof.get('ScopusID'))
        return status, None
    except FolderCreationError as exc:
        current_app.logger.warning(
            'Folder healing failed for professor %s: %s',
            professor_key, exc)
        return None, str(exc)


def refresh_personal_files(professor_key, professor_folder):
    """
    Rewrite the DERIVED PersonalData files — ContactInfo.tex and
    personal_data.txt — from the professor's current database record.

    These are generated files, not authored ones: they belong to the
    same family as the Excel exports and scholarship.bib, which are
    rebuilt from the database on every generation. Writing them only at
    folder creation left every pre-existing folder (professor 1,
    migrated during the ID-path redesign; every future s-drive import)
    carrying the scaffold template's placeholders — a CV headed
    "Jane U. Doe", a FAR whose \\mynames bolded the wrong author, and
    blank publication IDs that would silently starve the ORCID sync.

    Refreshing here also means a professor who edits their name or email
    sees it in the next document with no repair action.

    Returns True on success, False if the professor is unknown or the
    files could not be written. Never raises: a refresh failure must not
    cost someone their generation.
    """
    prof = execute_query(
        'SELECT FirstName, LastName, GoogleID, ORCID, ScopusID '
        'FROM PROFESSOR WHERE ProfessorKey = %s',
        (professor_key,), fetchone=True)
    if not prof:
        current_app.logger.warning(
            'Cannot refresh personal files: professor %s not found',
            professor_key)
        return False

    user = execute_query(
        'SELECT Email FROM users WHERE ProfessorKey = %s',
        (professor_key,), fetchone=True)
    email = (user or {}).get('Email') or ''

    personal_dir = os.path.join(professor_folder, 'make_cv', 'PersonalData')
    try:
        os.makedirs(personal_dir, exist_ok=True)
        # personal_data.txt is pure key-value data the app owns outright.
        # ContactInfo.tex may have been hand-authored (phone, LinkedIn,
        # webpage - fields the DB has no column for), so only refresh it
        # when it is ours or untouched.
        contact_path = os.path.join(personal_dir, 'ContactInfo.tex')
        if contactinfo_is_app_owned(contact_path):
            render_contactinfo(
                contact_path,
                prof.get('FirstName') or '', prof.get('LastName') or '', email)
        else:
            current_app.logger.info(
                'Left hand-edited ContactInfo.tex alone for professor %s',
                professor_key)
        write_personal_data(
            os.path.join(personal_dir, 'personal_data.txt'),
            prof.get('GoogleID'), prof.get('ORCID'), prof.get('ScopusID'))
        return True
    except Exception as exc:
        current_app.logger.warning(
            'Could not refresh personal files for professor %s: %s',
            professor_key, exc)
        return False
