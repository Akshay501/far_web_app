# Faculty Activity Report (FAR) Web App

A full-stack web application that lets university faculty manage their
Faculty Activity Report (FAR) data and generate formatted PDF reports.

Professors log in, maintain their teaching, service, grants, advising, and
scholarship data through a structured web interface, and generate a
polished FAR on demand. The application handles data storage, publication
management (including BibTeX import), and a LaTeX-based typesetting pipeline
that turns the stored data into a formatted PDF.

---

## Features

- **Role-based authentication** — separate professor and admin roles, with
  route-level access control and hashed credentials.
- **Professor dashboard** — manage data across all FAR sections: teaching,
  service, grants and proposals, advising, awards, and scholarship.
- **Publication management** — import publications from BibTeX, edit them
  in place, and categorize them (journal, conference, book, patent, etc.).
- **Per-author student-marker editor** — mark individual co-authors as
  graduate or undergraduate students; the markers flow through to the
  generated report's publication list.
- **PDF report generation** — produce a formatted FAR with a table of
  contents, per-section tables, and a configurable year range, via a
  LaTeX-based typesetting pipeline.
- **Standalone mode** — a no-login flow for uploading data files, editing,
  and generating a report without an account.

## Tech Stack

- **Backend:** Python, Flask, Flask-Login, Flask-WTF (CSRF protection)
- **Database:** MySQL (via PyMySQL) — 19 relational tables, one per FAR
  data domain
- **Frontend:** Jinja2 templates, Bootstrap 5, jQuery, DataTables
- **Data & documents:** openpyxl (Excel export), bibtexparser (BibTeX),
  a LaTeX-based PDF generation pipeline
- **Testing:** pytest

## Architecture

The application separates concerns into three layers:

1. **Web layer** — Flask routes organized into blueprints (auth, professor,
   admin, generate, standalone), server-rendered with Jinja2.
2. **Data layer** — a MySQL database with one table per FAR section, plus
   professor and user tables. The app reads and writes this store as the
   single source of truth.
3. **Generation layer** — at report time, the app exports the relevant
   database rows into the structured files the typesetting pipeline
   expects, then invokes it to produce the final PDF.

The everyday path (browsing and editing) touches only the web and data
layers. The generation layer is engaged only when a report is produced,
which keeps the interactive experience fast and the generation logic
isolated.

## Testing

The project includes an automated test suite (52 tests) run with `pytest`:

- **Authentication** — login success and failure, and access control on
  protected routes.
- **Marker editor** — verifies that student markers are stored correctly
  and that display fields stay clean.
- **Export contract** — verifies that every data file the generation
  pipeline reads is produced with the correct name, location, sheet, and
  columns. This guards against silent breakage when the pipeline changes.
- **Smoke tests** — confirm the app builds and core pages render.

Tests run against a dedicated test database, isolated from production data.

Slower, environment-dependent checks — such as full PDF generation, which
requires a LaTeX toolchain — are verified through a separate manual process.

```bash
pytest -v
```

## Installation

### Requirements

- Python 3.12+
- A MySQL database
- A LaTeX toolchain (`xelatex` + `biber`) for PDF generation
- Python packages listed in `requirements.txt`

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Akshay501/far_web_app.git
   cd far_web_app
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create `config.yml`** in the project root (not committed to version
   control — see `config_example.yml` for the structure). It holds the
   database connection details and the path to the report data folder.

4. **Run the app**
   ```bash
   python run.py
   ```
   The app is served at `http://localhost:5000`.

## Roadmap

Planned work is tracked in
[GitHub Issues](https://github.com/Akshay501/far_web_app/issues). Highlights:

- **CV generation** — full CV output alongside the FAR.
- **Publication sync** — pull new publications from Google Scholar, ORCID,
  and Scopus into a professor's library.
- **Full filesystem export** — download a professor's complete data folder
  as a portable archive.
- **Batch generation** — generate reports for all professors at once (admin).
- **ProQuest thesis importer** — import thesis/advisee data from ProQuest.
- **Application logging** — structured logging throughout.

## Project Status

Under active development as a graduate project at Clarkson University.
The core application — authentication, data management, publication
handling, and report generation — is functional and tested. See the
roadmap above for planned features.
