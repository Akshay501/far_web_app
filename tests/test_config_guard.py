"""
The FAR config guard (fallout from the 2026-07-30 batch hangs).

make_cv's create_config runs in TWO places: our ensure_config_updated
repairs an incomplete cfg with it, and make_far's own main() runs it at
generation time if the cfg is missing or incomplete. Its defaults plant
two mines in a FAR config:

  GoogleStats/ScopusStats = true   -> per-publication citation scrape,
                                      no timeout upstream (the hang)
  References = false               -> a CV-only section; FAR.sty defines
                                      no such boolean, LaTeX errors, and
                                      make_far's missing
                                      -interaction=batchmode turns the
                                      error into a ? prompt waiting
                                      forever for keyboard input

The guard lives INSIDE ensure_config_updated so every caller (single
generate, batch, export) is protected: after any repair — and after
CREATING a missing cfg, which previously fell through to make_far's
unguarded creator — a FAR config is forced to references=true and
stats=false. CV configs are left alone: a CV legitimately excludes its
References section.

FAR-vs-CV is decided by the config's own latexfile (far.tex vs cv.tex),
falling back to the folder name.
"""
import configparser
import os

import pytest


MINIMAL_ARMED = (
    '[CV]\n'
    'years = 1\n'
    'latexfile = far.tex\n'
    'googlestats = true\n'
    'scopusstats = true\n'
    'references = false\n'
)


def _read(path):
    cfg = configparser.ConfigParser()
    cfg.read(path)
    sec = cfg.sections()[0]
    return cfg, sec


def test_repair_guards_a_far_config(app, tmp_path):
    """An incomplete FAR cfg triggers the create_config repair, whose
    defaults re-arm the mines — the guard must defuse both afterwards."""
    from app.routes.generate import ensure_config_updated

    far = tmp_path / 'FAR'
    far.mkdir()
    (far / 'make_cv.cfg').write_text(MINIMAL_ARMED)

    with app.app_context():
        ensure_config_updated(str(far))

    cfg, sec = _read(far / 'make_cv.cfg')
    assert cfg.get(sec, 'references') == 'true', \
        'References must be neutralised in a FAR config'
    assert cfg.get(sec, 'googlestats') == 'false'
    assert cfg.get(sec, 'scopusstats') == 'false'


def test_cv_config_is_left_alone(app, tmp_path):
    """references=false is CORRECT for a CV — the guard must not touch
    a CV config."""
    from app.routes.generate import ensure_config_updated

    cv = tmp_path / 'CV'
    cv.mkdir()
    (cv / 'make_cv.cfg').write_text(
        MINIMAL_ARMED.replace('latexfile = far.tex', 'latexfile = cv.tex'))

    with app.app_context():
        ensure_config_updated(str(cv))

    cfg, sec = _read(cv / 'make_cv.cfg')
    assert cfg.get(sec, 'references') == 'false', \
        'a CV config must keep its legitimate references=false'


def test_missing_far_config_is_created_and_guarded(app, tmp_path):
    """Previously ensure returned early on a missing cfg, handing
    creation to make_far's UNGUARDED create_config at generation time.
    Now ensure creates it — guarded, with the right latexfile."""
    from app.routes.generate import ensure_config_updated

    far = tmp_path / 'FAR'
    far.mkdir()

    with app.app_context():
        ensure_config_updated(str(far))

    path = far / 'make_cv.cfg'
    assert path.exists(), 'ensure must create a missing cfg itself'
    cfg, sec = _read(path)
    assert cfg.get(sec, 'latexfile') == 'far.tex', \
        'a cfg created in a FAR folder must point at far.tex'
    assert cfg.get(sec, 'references') == 'true'
    assert cfg.get(sec, 'googlestats') == 'false'
    assert cfg.get(sec, 'scopusstats') == 'false'


def test_single_generate_route_is_guarded(app, logged_in_client,
                                          seed_professor, scaffold,
                                          monkeypatch):
    """The route-level proof for the SINGLE generate page — batch has
    its own test. An armed cfg must come out defused after a generate
    POST, whatever generation itself did."""
    import app.routes.generate as gen
    monkeypatch.setattr(gen, 'run_make_far',
                        lambda *a, **k: (False, 'stubbed by test'))
    monkeypatch.setattr(gen, 'export_all', lambda *a, **k: None)

    far = scaffold['root'] / str(seed_professor['professor_key']) \
        / 'make_cv' / 'FAR'
    far.mkdir(parents=True, exist_ok=True)
    (far / 'make_cv.cfg').write_text(MINIMAL_ARMED)

    logged_in_client.post('/generate', data={
        'doc_type': 'far', 'years': '1', 'format': 'pdf',
    }, follow_redirects=True)

    cfg, sec = _read(far / 'make_cv.cfg')
    assert cfg.get(sec, 'references') == 'true'
    assert cfg.get(sec, 'googlestats') == 'false'
    assert cfg.get(sec, 'scopusstats') == 'false'
