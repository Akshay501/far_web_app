# app/excel_export.py
# Exports DB data to Excel files in the exact format make_cv expects.
# Column names must exactly match what make_cv reads — verified from source.

import os
import openpyxl
from openpyxl import Workbook
from datetime import datetime


def _wb(headers):
    """Create a workbook with a Data sheet and given headers."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(headers)
    return wb, ws


def write_personal_awards(path, rows):
    """
    PERSONALAWARDS joined with AWARDS
    make_cv expects: Title, Type, Year
    """
    wb, ws = _wb(['Title', 'Type', 'Year'])
    for r in rows:
        ws.append([
            r.get('Title', ''),
            r.get('Award Type', ''),
            r.get('Year', ''),
        ])
    wb.save(path)


def write_student_awards(path, rows):
    """
    STUDENTAWARDS joined with AWARDS
    make_cv expects: Student, Title, Amount, Category, Type, Year
    """
    wb, ws = _wb(['Student', 'Title', 'Amount', 'Category', 'Type', 'Year'])
    for r in rows:
        ws.append([
            r.get('Student', ''),
            r.get('Title', ''),
            r.get('Amount', 0),
            r.get('Category', ''),
            r.get('Award Type', ''),
            r.get('Year', ''),
        ])
    wb.save(path)


def write_proposals_and_grants(path, rows):
    """
    PROPOSAL + GRANTS combined
    make_cv expects: Sponsor, Allocated Amt, Total Cost, Funded?,
                     Title, Begin Date, End Date, Submit Date,
                     Principal Investigators
    """
    wb, ws = _wb([
        'Sponsor', 'Allocated Amt', 'Total Cost', 'Funded?',
        'Title', 'Begin Date', 'End Date', 'Submit Date',
        'Principal Investigators'
    ])
    for r in rows:
        funded = 'Y' if r.get('Funded?') in (1, True, 'Y', 'y', '1') else 'N'
        ws.append([
            r.get('Sponsor', ''),
            r.get('Allocated Amount', 0) or 0,
            r.get('Total Cost', 0) or 0,
            funded,
            r.get('Title', ''),
            r.get('Begin Date', None),
            r.get('End Date', None),
            r.get('Submit Date', None),
            r.get('Principal Investigator', '') or r.get('Principal Investigators', ''),
        ])
    wb.save(path)


def write_grants(path, rows):
    """
    GRANTS only (funded only)
    make_cv expects: Sponsor, Allocated Amt, Total Cost, Funded?,
                     Title, Begin Date, End Date, Submit Date,
                     Principal Investigators
    """
    funded_rows = [r for r in rows if r.get('Funded?') in (1, True, 'Y', 'y', '1')]
    write_proposals_and_grants(path, funded_rows)


def write_expenditures(path, rows):
    """
    EXPENDITURE
    make_cv reads last row: Year, Name, Expenditure, Indirect, Tuition, Salary Recovery
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(['Year', 'Name', 'Expenditure', 'Indirect', 'Tuition', 'Salary Recovery'])
    for r in rows:
        ws.append([
            r.get('Year', ''),
            r.get('Name', ''),
            r.get('Expenditure', 0) or 0,
            r.get('Indirect', 0) or 0,
            r.get('Tuition', 0) or 0,
            r.get('Salary Recovery', 0) or 0,
        ])
    wb.save(path)


def write_current_students(path, rows):
    """
    CURRENTSTUDENTS
    make_cv expects: Student Name, Current Program, Start Date
    """
    wb, ws = _wb(['Student Name', 'Current Program', 'Start Date'])
    for r in rows:
        ws.append([
            r.get('Student Name', ''),
            r.get('Current Program', ''),
            r.get('Start Date', None),
        ])
    wb.save(path)


def write_thesis(path, rows):
    """
    THESIS
    make_cv expects: Student, Year, Degree, Title, Comments
    """
    wb, ws = _wb(['Student', 'Year', 'Degree', 'Title', 'Comments'])
    for r in rows:
        ws.append([
            r.get('Student Name', ''),
            r.get('Year', ''),
            r.get('Degree', ''),
            r.get('Title', ''),
            r.get('Comments', ''),
        ])
    wb.save(path)


def write_service(path, rows):
    """
    SERVICE
    make_cv expects: Description, Type, Position, Term, Calendar Year,
                     Hours/Semester, Comments
    """
    wb, ws = _wb([
        'Description', 'Type', 'Position', 'Term',
        'Calendar Year', 'Hours/Semester', 'Comments'
    ])
    for r in rows:
        hours = r.get('Hours/Semester')
        ws.append([
            r.get('Description', ''),
            r.get('Type', ''),
            r.get('Position', ''),
            r.get('Term', ''),
            r.get('Calendar Year', ''),
            float(hours) if hours is not None else None,
            r.get('Comments', ''),
        ])
    wb.save(path)


def write_reviews(path, rows):
    """
    REVIEWS
    make_cv expects: Journal, Start, Rounds
    """
    wb, ws = _wb(['Journal', 'Start', 'Rounds'])
    for r in rows:
        ws.append([
            r.get('Journal', ''),
            r.get('Start Date', None),
            r.get('Rounds', 0) or 0,
        ])
    wb.save(path)


def write_professional_development(path, rows):
    """
    PROFESSIONALDEVELOPMENT
    make_cv expects: Description, Type, Term, Calendar Year, Hours, Notes
    """
    wb, ws = _wb(['Description', 'Type', 'Term', 'Calendar Year', 'Hours', 'Notes'])
    for r in rows:
        ws.append([
            r.get('Description', ''),
            r.get('Type', ''),
            r.get('Term', ''),
            r.get('Calendar Year', ''),
            r.get('Hours', 0) or 0,
            r.get('Notes', ''),
        ])
    wb.save(path)


def write_undergraduate_research(path, rows):
    """
    UNDERGRADUATERESEARCH
    make_cv expects: Students, Title, Program Type, Term, Calendar Year
    """
    wb, ws = _wb(['Students', 'Title', 'Program Type', 'Term', 'Calendar Year'])
    for r in rows:
        ws.append([
            r.get('Students', ''),
            r.get('Title', ''),
            r.get('Program Type', ''),
            r.get('Term', ''),
            r.get('Calendar Year', ''),
        ])
    wb.save(path)


def write_advisee_counts(path, rows):
    """
    ADVISEECOUNT
    make_far reads last row: Advisor Name, Count Distinct Name, YEAR
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(['Advisor Name', 'Count Distinct Name', 'YEAR'])
    for r in rows:
        ws.append([
            r.get('Advisor Name', ''),
            r.get('Advisee Count', 0) or 0,
            r.get('Year', ''),
        ])
    wb.save(path)


def write_advising_evaluation(path, rows):
    """
    ADVISINGEVALUATION — pass through all columns as-is
    make_cv reads this file but exact columns vary; write what we have.
    """
    if not rows:
        return
    headers = list(rows[0].keys())
    wb, ws = _wb(headers)
    for r in rows:
        ws.append([r.get(h, '') for h in headers])
    wb.save(path)


def write_teaching_evaluation(path, rows):
    """
    TEACHINGEVALUATION
    Exact column names from Langen Tom's real teaching evaluation data.xlsx:
    STRM, term, school, course, course_num, course_section, course_title,
    INSTR_NA, ID, count_evals, enrollment, Particip, question,
    a1, a1_pct, a2, a2_pct, a3, a3_pct, a4, a4_pct, a5, a5_pct,
    na, na_pct, Calculated Mean, Question, combined_course_num, Weighted Average
    """
    wb, ws = _wb([
        'STRM', 'term', 'school', 'course', 'course_num',
        'course_section', 'course_title', 'INSTR_NA', 'ID',
        'count_evals', 'enrollment', 'Particip', 'question',
        'a1', 'a1_pct', 'a2', 'a2_pct', 'a3', 'a3_pct',
        'a4', 'a4_pct', 'a5', 'a5_pct', 'na', 'na_pct',
        'Calculated Mean', 'Question', 'combined_course_num',
        'Weighted Average'
    ])
    for r in rows:
        ws.append([
            r.get('STRM', ''),
            r.get('Term', ''),
            r.get('School', ''),
            r.get('Course', '') or r.get('Course Number', ''),
            r.get('Course Number', ''),
            r.get('Course Section', ''),
            r.get('Course Title', ''),
            r.get('INSTR_NA', ''),
            r.get('ID', ''),
            r.get('Count Evals', 0) or 0,
            r.get('Enrolment', 0) or 0,
            r.get('Participation', 0) or 0,
            r.get('question', '') or r.get('Question', ''),
            r.get('a1', 0) or 0,
            r.get('a1_pct', 0) or 0,
            r.get('a2', 0) or 0,
            r.get('a2_pct', 0) or 0,
            r.get('a3', 0) or 0,
            r.get('a3_pct', 0) or 0,
            r.get('a4', 0) or 0,
            r.get('a4_pct', 0) or 0,
            r.get('a5', 0) or 0,
            r.get('a5_pct', 0) or 0,
            r.get('na', 0) or 0,
            r.get('na_pct', 0) or 0,
            r.get('Calculated Mean', 0) or 0,
            r.get('question', '') or r.get('Question', ''),
            r.get('Combined Course Number', '') or r.get('ID', ''),
            r.get('Weighted Average', 0) or 0,
        ])
    wb.save(path)


def write_prospective_visits(path, rows):
    """
    PROSPECTIVEVISIT
    make_far reads: Visits, Deposits, Year from last row
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(['Year', 'Staff', 'Visits', 'Deposits'])
    for r in rows:
        ws.append([
            r.get('Year', ''),
            r.get('Staff', ''),
            r.get('Visits', 0) or 0,
            r.get('Deposits', 0) or 0,
        ])
    wb.save(path)


def export_all(professor_key, professor_folder, db_data):
    """
    Write all Excel files for a professor into the correct subfolders.

    professor_folder: path like /path/to/Departments/Dept/Last, First
    db_data: dict with keys matching table names, values are lists of row dicts
    """
    def ensure(subfolder):
        p = os.path.join(professor_folder, subfolder)
        os.makedirs(p, exist_ok=True)
        return p

    awards_dir  = ensure('Awards')
    grants_dir  = ensure('Proposals & Grants')
    scholar_dir = ensure('Scholarship')
    service_dir = ensure('Service')
    teach_dir   = ensure('Teaching')

    write_personal_awards(
        os.path.join(awards_dir, 'personal awards data.xlsx'),
        db_data.get('personal_awards', [])
    )
    write_student_awards(
        os.path.join(awards_dir, 'student awards data.xlsx'),
        db_data.get('student_awards', [])
    )
    write_proposals_and_grants(
        os.path.join(grants_dir, 'proposals & grants.xlsx'),
        db_data.get('proposals', [])
    )
    write_grants(
        os.path.join(grants_dir, 'grants.xlsx'),
        db_data.get('grants', [])
    )
    write_expenditures(
        os.path.join(grants_dir, 'expenditures.xlsx'),
        db_data.get('expenditures', [])
    )
    write_current_students(
        os.path.join(scholar_dir, 'current student data.xlsx'),
        db_data.get('current_students', [])
    )
    write_thesis(
        os.path.join(scholar_dir, 'thesis data.xlsx'),
        db_data.get('thesis', [])
    )
    write_service(
        os.path.join(service_dir, 'service data.xlsx'),
        db_data.get('service', [])
    )
    write_reviews(
        os.path.join(service_dir, 'reviews data.xlsx'),
        db_data.get('reviews', [])
    )
    write_professional_development(
        os.path.join(service_dir, 'professional development data.xlsx'),
        db_data.get('prof_development', [])
    )
    write_undergraduate_research(
        os.path.join(service_dir, 'undergraduate research data.xlsx'),
        db_data.get('undergrad_research', [])
    )
    write_advisee_counts(
        os.path.join(service_dir, 'advisee counts.xlsx'),
        db_data.get('advisee_counts', [])
    )
    if db_data.get('advising_evals'):
        write_advising_evaluation(
            os.path.join(service_dir, 'advising evaluation data.xlsx'),
            db_data.get('advising_evals', [])
        )
    write_teaching_evaluation(
        os.path.join(teach_dir, 'teaching evaluation data.xlsx'),
        db_data.get('teaching', [])
    )
    write_prospective_visits(
        os.path.join(service_dir, 'prospective visit data.xlsx'),
        db_data.get('prospective_visits', [])
    )
