"""
Issue #12: generation must run in a SUBPROCESS with a timeout.

run_make_far used to import make_far and call it in-process. That means
a hang inside make_far — LaTeX waiting at a "?" prompt for keyboard
input, a network call with no limit — is a hang inside the web worker,
with no way for the app to notice, log, or recover. Both happened live
on 2026-07-30, and both froze the entire batch until Ctrl-C.

As a subprocess, the app keeps control: it starts generation, watches
the clock, kills the process when the budget expires, and reports
"timed out" on that professor's row. One bad folder becomes one bad row
instead of a dead server. Captured output means a failure's actual
error text reaches the results table instead of vanishing into the
console.

These tests never run the real make_far: they monkeypatch the command
builder to point at tiny inline Python scripts, so they are fast,
hermetic, and safe to run anywhere.
"""
import sys
import time

import pytest


def _fake(script):
    """A command list running an inline python script."""
    return [sys.executable, '-c', script]


def test_success_returns_ok(app, monkeypatch, tmp_path):
    import app.routes.generate as gen
    monkeypatch.setattr(gen, '_generation_command',
                        lambda module, extra_args=(): _fake('print("done")'))

    with app.app_context():
        ok, err = gen.run_make_far(str(tmp_path))

    assert ok is True
    assert err is None


def test_hang_is_killed_and_reported(app, monkeypatch, tmp_path):
    """THE issue-#12 behaviour: a process that would run forever is
    stopped at the budget and reported as a timeout — quickly."""
    import app.routes.generate as gen
    monkeypatch.setattr(gen, '_generation_command',
                        lambda module, extra_args=(): _fake(
                            'import time; time.sleep(60)'))

    app.config['GENERATION_TIMEOUT'] = 1
    start = time.monotonic()
    with app.app_context():
        ok, err = gen.run_make_far(str(tmp_path))
    elapsed = time.monotonic() - start

    assert ok is False
    assert 'timed out' in (err or '').lower()
    assert elapsed < 10, 'the app must reclaim control at the budget'


def test_failure_output_reaches_the_error(app, monkeypatch, tmp_path):
    """When generation fails, the actual error text must surface in the
    returned message — not vanish into a console nobody is watching."""
    import app.routes.generate as gen
    monkeypatch.setattr(gen, '_generation_command',
                        lambda module, extra_args=(): _fake(
                            'import sys; '
                            'print("! LaTeX Error: something broke", '
                            'file=sys.stderr); sys.exit(1)'))

    with app.app_context():
        ok, err = gen.run_make_far(str(tmp_path))

    assert ok is False
    assert 'LaTeX Error' in err, 'the captured output must be surfaced'


def test_runs_in_the_far_folder(app, monkeypatch, tmp_path):
    """The subprocess must execute IN the professor's FAR folder — that
    is where make_far expects its config and writes its output."""
    import app.routes.generate as gen
    monkeypatch.setattr(gen, '_generation_command',
                        lambda module, extra_args=(): _fake(
                            'import os; '
                            'open("cwd.txt", "w").write(os.getcwd())'))

    with app.app_context():
        ok, _ = gen.run_make_far(str(tmp_path))

    assert ok is True
    recorded = (tmp_path / 'cwd.txt').read_text()
    assert recorded.rstrip('/').endswith(tmp_path.name), \
        'generation must run inside the given folder'


def test_pandoc_flag_is_passed_through(app, monkeypatch, tmp_path):
    import app.routes.generate as gen
    seen = {}

    def spy(module, folder, extra_args=(), what='generation'):
        seen['module'] = module
        seen['extra'] = tuple(extra_args)
        return True, None
    monkeypatch.setattr(gen, '_run_generation', spy)

    with app.app_context():
        gen.run_make_far(str(tmp_path), use_pandoc=True)

    assert seen['module'] == 'make_cv.make_far'
    assert '-p' in seen['extra']


def test_output_is_streamed_live_and_captured(app, monkeypatch, tmp_path,
                                              capsys):
    """Show it AND capture it: each line the generator prints must
    appear on the app's console as it happens (streamed), and still be
    available in the error message when the run fails (captured)."""
    import app.routes.generate as gen
    monkeypatch.setattr(gen, '_generation_command',
                        lambda module, extra_args=(): _fake(
                            'import sys; print("marker-LINE-42", flush=True); '
                            'sys.exit(1)'))

    with app.app_context():
        ok, err = gen.run_make_far(str(tmp_path))

    assert ok is False
    assert 'marker-LINE-42' in err, 'captured for the error message'
    assert 'marker-LINE-42' in capsys.readouterr().out, \
        'streamed live to the console as it happened'


def test_timeout_message_includes_partial_output(app, monkeypatch, tmp_path):
    """A timeout must show how far the run got — the partial output is
    the only clue to WHERE it hung."""
    import app.routes.generate as gen
    monkeypatch.setattr(gen, '_generation_command',
                        lambda module, extra_args=(): _fake(
                            'import time; '
                            'print("reached-typesetting", flush=True); '
                            'time.sleep(60)'))

    app.config['GENERATION_TIMEOUT'] = 1
    with app.app_context():
        ok, err = gen.run_make_far(str(tmp_path))

    assert ok is False
    assert 'timed out' in err.lower()
    assert 'reached-typesetting' in err, \
        'the partial output must accompany the timeout report'


def test_child_runs_unbuffered(app):
    """The child MUST run with -u: a python child writing into a pipe
    block-buffers its prints, so progress lines arrive inverted (after
    the grandchildren's output) — proven live 2026-08-17, where
    "Output written on far.pdf" appeared BEFORE "typesetting pass 1".
    Worse, a HUNG child never flushes, so the timeout report loses the
    very lines that say where it hung."""
    import app.routes.generate as gen
    cmd = gen._generation_command('make_cv.make_far')
    assert '-u' in cmd, 'child must be unbuffered for live, ordered output'


def test_timeout_kills_the_whole_process_group(app, monkeypatch, tmp_path):
    """The likeliest hanger is a GRANDCHILD (xelatex at its ? prompt).
    Killing only the middle python would orphan it, still holding
    far.pdf. The timeout must take down the whole group."""
    import os
    import app.routes.generate as gen
    monkeypatch.setattr(gen, '_generation_command',
                        lambda module, extra_args=(): _fake(
                            'import subprocess, sys\n'
                            'g = subprocess.Popen([sys.executable, "-c", '
                            '"import time; time.sleep(60)"])\n'
                            'open("gpid.txt", "w").write(str(g.pid))\n'
                            'g.wait()\n'))

    app.config['GENERATION_TIMEOUT'] = 1
    with app.app_context():
        ok, err = gen.run_make_far(str(tmp_path))

    assert ok is False and 'timed out' in err.lower()
    gpid = int((tmp_path / 'gpid.txt').read_text())
    for _ in range(30):                      # allow up to ~3s to die
        try:
            os.kill(gpid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            break
    else:
        os.kill(gpid, 9)                     # clean up, then fail
        raise AssertionError('grandchild survived the timeout')
