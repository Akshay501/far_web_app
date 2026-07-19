# far_web_app
A modern, full-stack web application for Clarkson University professors to manage their Faculty Activity Reports (FAR). 

# Faculty Activity Report (FAR) Web App

![FAR Dashboard]('/Users/akshaythugudam/Documents/GitHub/FAR/FAR_Dashboard/static/images/FAR_Loginpage.png')  

A data-driven web application for professors to view, update, and export their Faculty Activity Reports. Built with Flask, MySQL, and Bootstrap, featuring login, dashboards, BibTeX imports for publications, and PDF generation.

## Features
- **User Authentication**: Separate logins for professors and admins 
- **Professor Dashboard**: Tabs for Teaching, Service, Grants, and Scholarly Output (with add/import/edit).
- **Admin Dashboard**: Search/filter/view professors.
- **Scholarly Outputs**: Flexible JSON storage with BibTeX parsing (no rigid DB tables).
- **PDF Export**: Generates formatted reports with dynamic TOC, sections, and counts 
- **Database Integration**: Connects to MySQL for storing/retrieving data.

## Tech Stack
- Python/Flask for backend.
- MySQL/PyMySQL for database.
- Bootstrap/Jinja for frontend.
- fpdf for PDF generation.
- bibtexparser for citation imports.

## Installation
### Requirements
- Python 3.12+ (tested on 3.12).
- MySQL database (e.g., local or remote like mysql.clarksonmsda.org).
- The following Python packages (listed in requirements.txt):
  - Flask==3.0.3 (web framework)
  - Flask-Login==0.6.3 (authentication)
  - pymysql==1.1.1 (MySQL connector)
  - PyYAML==6.0.2 (config loading)
  - Werkzeug==3.0.4 (utilities, including password hashing)
  - fpdf==1.7.2 (PDF generation)
  - bibtexparser==1.4.1 (BibTeX parsing for publications)

### Setup Steps
1. **Clone the Repository**:

git clone https://github.com/yourusername/faculty-activity-report.git
cd faculty-activity-report

2. **Install Dependencies**:
Create a virtual environment (recommended) and install packages:

python -m venv venv
source venv/bin/activate  # On Mac/Linux; on Windows: venv\Scripts\activate
pip install -r requirements.txt


3. **Configure the Database**:
- Create your MySQL database (e.g., `YOURNAME_FAR`).
- Run your SQL scripts to create tables (from ERD_Diagrams or screenshots).
- Edit `config.yml` with your DB details (user, pw, host, db).
- Add the ScholarlyOutputs column: `ALTER TABLE PROFESSOR ADD COLUMN ScholarlyOutputs JSON DEFAULT NULL;`

4. **Run the App**:
python app.py

- Visit http://127.0.0.1:5000 in your browser.
- Default login: Use credentials from `users` table (e.g., admin@far-system.edu / admin123)


## License
MIT License. See LICENSE file.

## Contributors
- Akshay Thugudam (Clarkson University)