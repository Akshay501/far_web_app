import pymysql
import pymysql.cursors
import yaml
import os
from flask import g, current_app


def load_config():
    with open('config.yml', 'r') as f:
        return yaml.safe_load(f)


def get_db():
    """Return a per-request DB connection, reusing it if already open."""
    if 'db' not in g:
        cfg = current_app.config['DB_CONFIG']
        g.db = pymysql.connect(
            host=cfg['host'],
            user=cfg['user'],
            password=cfg['pw'],
            db=cfg['db'],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    return g.db


def close_db(e=None):
    """Close DB connection at end of request. Registered in create_app()."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def execute_query(query, args=None, fetchone=False, commit=False, lastrowid=False):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, args or ())
    if commit:
        db.commit()
    if lastrowid:
        # For INSERTs: the auto-generated key of the new row.
        result = cursor.lastrowid
    else:
        result = cursor.fetchone() if fetchone else cursor.fetchall()
    cursor.close()
    return result


def import_excel_to_table(file_path, table_name, professor_key, mapping):
    import openpyxl
    wb = openpyxl.load_workbook(file_path)
    sheet = wb['Data']
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    db = get_db()
    cursor = db.cursor()
    for row in rows:
        if not row[0]:
            continue
        data = dict(zip(mapping.keys(), row))
        data['ProfessorKey'] = professor_key
        cols = ', '.join(data.keys())
        vals = ', '.join(['%s'] * len(data))
        query = f"INSERT INTO {table_name} ({cols}) VALUES ({vals})"
        cursor.execute(query, tuple(data.values()))
    db.commit()
    cursor.close()


def safe_slug(value, fallback='unknown'):
    """
    Filesystem- and header-safe slug: ascii lowercase, spaces become
    underscores, and only letters/digits/underscore/hyphen survive —
    never empty. Accents are transliterated (José -> jose); anything
    that could act as a path or quote character is dropped. Used for
    download filenames (Issue #7 and the far.pdf naming issue).
    """
    import re
    import unicodedata

    text = unicodedata.normalize('NFKD', str(value or ''))
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = text.lower().strip()
    text = re.sub(r'\s+', '_', text)
    text = re.sub(r'[^a-z0-9_-]', '', text)
    return text or fallback
