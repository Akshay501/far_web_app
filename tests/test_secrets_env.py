"""
Phase 2 step 1: secrets come from the environment (.env), config.yml is
the fallback so nothing breaks before migration.

Precedence: real environment > .env file (load_dotenv never overrides
an existing variable) > config.yml. The password already sitting in git
history is steps 2-3 (rotate, purge); this step is the foundation they
need — and the home the Scopus key has been waiting for.
"""
import subprocess

import yaml

from app import create_app


def test_db_password_prefers_the_environment(monkeypatch):
    monkeypatch.setenv('FAR_DB_PASSWORD', 'password-from-env')
    app = create_app()
    assert app.config['DB_CONFIG']['pw'] == 'password-from-env'


def test_db_password_falls_back_to_yaml(monkeypatch):
    """Until .env exists, config.yml keeps working — Brian's setup and
    the container must not break the day this lands."""
    monkeypatch.delenv('FAR_DB_PASSWORD', raising=False)
    app = create_app()
    with open('config.yml') as f:
        expected = yaml.safe_load(f)['db']['pw']
    assert app.config['DB_CONFIG']['pw'] == expected


def test_scopus_key_reaches_app_config(monkeypatch):
    monkeypatch.setenv('FAR_SCOPUS_API_KEY', 'k-12345')
    app = create_app()
    assert app.config['SCOPUS_API_KEY'] == 'k-12345'

    monkeypatch.delenv('FAR_SCOPUS_API_KEY')
    app = create_app()
    assert app.config['SCOPUS_API_KEY'] is None


def test_default_secret_key_warns(monkeypatch, caplog):
    """The committed fallback SECRET_KEY means forgeable sessions; the
    app must say so at startup rather than stay silent.

    Config reads the environment at IMPORT time, so delenv here would
    be too late — and on a developer machine with a real .env the class
    attribute already holds the real key. Patch the attribute directly:
    the warning logic is what's under test, not dotenv's loading.
    """
    import logging

    from app.config import Config
    monkeypatch.setattr(Config, 'SECRET_KEY', 'clarkson-far-2026-secret-key')

    with caplog.at_level(logging.WARNING):
        create_app()
    assert any('SECRET_KEY' in r.message for r in caplog.records), \
        'running on the default secret key must produce a warning'


def test_real_secret_key_is_silent(monkeypatch, caplog):
    """The complement: a real key must NOT warn, or the warning becomes
    noise everyone learns to ignore."""
    import logging

    from app.config import Config
    monkeypatch.setattr(Config, 'SECRET_KEY', 'a-real-64-char-key')

    with caplog.at_level(logging.WARNING):
        create_app()
    assert not any('SECRET_KEY' in r.message for r in caplog.records), \
        'a configured secret key must not produce the warning'


def test_ignore_rules_actually_ignore(tmp_path):
    """git check-ignore is the truth, not the .gitignore text: a fused
    line (missing newline) can silently disable a rule — found live
    2026-08-18 where '.cursorindexingignore' and 'config.yml' had
    merged into one broken entry."""
    for name in ('.env', 'config.yml'):
        rc = subprocess.run(['git', 'check-ignore', '-q', name]).returncode
        assert rc == 0, f'{name} must be git-ignored'
    with open('.env.example') as f:
        example = f.read()
    for var in ('FAR_DB_PASSWORD', 'FAR_SCOPUS_API_KEY', 'SECRET_KEY'):
        assert var in example, f'.env.example must document {var}'
