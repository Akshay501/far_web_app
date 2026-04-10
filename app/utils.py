import pymysql
import yaml
import subprocess
import os
from datetime import datetime

def load_config():
    with open('config.yml', 'r') as f:
        return yaml.safe_load(f)

def get_db():
    cfg = load_config()['db']
    return pymysql.connect(
        host=cfg['host'],
        user=cfg['user'],
        password=cfg['pw'],
        db=cfg['db'],
        cursorclass=pymysql.cursors.DictCursor
    )

def execute_query(query, args=None, fetchone=False, commit=False):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(query, args or ())
    if commit:
        db.commit()
    result = cursor.fetchone() if fetchone else cursor.fetchall()
    cursor.close()
    db.close()
    return result

def generate_cv(professor_key):
    try:
        result = subprocess.run(
            ['python', '../make_cv/make_cv.py', str(professor_key)],
            capture_output=True, text=True, cwd=os.path.dirname(__file__)
        )
        if result.returncode == 0:
            return f"static/cv/FAR_{professor_key}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return None
    except Exception as e:
        print("CV generation error:", e)
        return None
    
def import_excel_to_table(file_path, table_name, professor_key, mapping):
    import openpyxl
    wb = openpyxl.load_workbook(file_path)
    sheet = wb['Data']
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    db = get_db()
    cursor = db.cursor()
    for row in rows:
        if not row[0]: continue
        data = dict(zip(mapping.keys(), row))
        data['ProfessorKey'] = professor_key
        cols = ', '.join(data.keys())
        vals = ', '.join(['%s'] * len(data))
        query = f"INSERT INTO {table_name} ({cols}) VALUES ({vals})"
        cursor.execute(query, tuple(data.values()))
    db.commit()
    cursor.close()
    db.close()