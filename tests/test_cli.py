"""Tests for the DocToc CLI: exit codes, JSON reports, and dry runs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest

from doctoc.cli import EXIT_DRIFT, EXIT_INPUT, EXIT_SUCCESS, run

START = "<!--TOC-->"
END = "<!--/TOC-->"


def _write(directory: str, name: str, content: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def workdir() -> str:
    with tempfile.TemporaryDirectory() as directory:
        yield directory


@pytest.fixture
def doc(workdir: str) -> str:
    return _write(
        workdir,
        "doc.md",
        "# Title\n\nIntro\n\n## Section\n\n### Sub\n",
    )


def _cli(argv: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.join(os.path.dirname(__file__), "..", "src"), env.get("PYTHONPATH", "")]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "doctoc", *argv],
        capture_output=True,
        text=True,
        cwd=cwd or workdir,
        env=env,
    )
    return completed.returncode, completed.stdout, completed.stderr


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def test_generate_updates_file(doc: str, workdir: str) -> None:
    rc = run(["generate", doc])
    assert rc == EXIT_SUCCESS
    assert START in _read(doc)


def test_generate_idempotent(doc: str) -> None:
    run(["generate", doc])
    rc = run(["generate", doc])
    assert rc == EXIT_SUCCESS


def test_generate_json_report(doc: str, capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["generate", doc, "--json"])
    assert rc == EXIT_SUCCESS
    report = json.loads(capsys.readouterr().out)
    assert report["version"] == "1.0.0"
    assert report["files"][0]["drifted"] is True


def test_generate_dry_run_does_not_write(doc: str) -> None:
    run(["generate", doc, "--dry-run"])
    assert START not in _read(doc)


def test_generate_dry_run_reports_drift(doc: str) -> None:
    rc = run(["generate", doc, "--dry-run", "--json"])
    assert rc == EXIT_DRIFT
    # drift is computed and surfaced, but files are untouched


def test_generate_with_depth(doc: str) -> None:
    rc = run(["generate", doc, "--max-depth", "2"])
    assert rc == EXIT_SUCCESS
    content = _read(doc)
    assert "- [Sub](sub)" not in content
    assert "- [Section](section)" in content


def test_generate_first_h1(doc: str) -> None:
    rc = run(["generate", doc, "--first-h1"])
    assert rc == EXIT_SUCCESS
    assert "- [Title](title)" in _read(doc)


def test_generate_invalid_max_depth(doc: str) -> None:
    rc = run(["generate", doc, "--max-depth", "7"])
    assert rc == EXIT_INPUT


def test_generate_bad_indent(doc: str) -> None:
    rc = run(["generate", doc, "--indent", ""])
    assert rc == EXIT_INPUT


def test_generate_missing_path(workdir: str) -> None:
    rc = run(["generate", "missing.md"])
    assert rc == EXIT_INPUT


def test_generate_binary_file(workdir: str) -> None:
    path = os.path.join(workdir, "bin.md")
    with open(path, "wb") as handle:
        handle.write(b"\x00\x01\x02")
    rc = run(["generate", path])
    assert rc == EXIT_INPUT


def test_generate_stale_link_fails_validation(doc: str) -> None:
    content = f"# Title\n\n{START}\n- [Ghost](#ghost)\n{END}\n\n## Section\n"
    _write(os.path.dirname(doc), "stale.md", content)
    rc = run(["generate", os.path.join(os.path.dirname(doc), "stale.md"), "--validate-links"])
    assert rc == EXIT_DRIFT


def test_generate_directory(workdir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(workdir, "a.md", "# A\n\n## X\n")
    _write(workdir, "b.md", "# B\n\n## Y\n")
    monkeypatch.chdir(workdir)
    rc = run(["generate", "."])
    assert rc == EXIT_SUCCESS
    assert START in _read(os.path.join(workdir, "a.md"))
    assert START in _read(os.path.join(workdir, "b.md"))


def test_generate_custom_indent(doc: str) -> None:
    rc = run(["generate", doc, "--indent", "    "])
    assert rc == EXIT_SUCCESS
    assert "    - [Sub](sub)" in _read(doc)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def test_check_clean(doc: str) -> None:
    run(["generate", doc])
    rc = run(["check", doc])
    assert rc == EXIT_SUCCESS


def test_check_drift(doc: str) -> None:
    rc = run(["check", doc])
    assert rc == EXIT_DRIFT


def test_check_never_writes(doc: str) -> None:
    run(["check", doc])
    assert START not in _read(doc)


def test_check_stale_links(doc: str) -> None:
    stale = os.path.join(os.path.dirname(doc), "stale.md")
    _write(
        os.path.dirname(doc),
        "stale.md",
        f"# Title\n\n{START}\n- [Ghost](#ghost)\n{END}\n\n## Section\n",
    )
    rc = run(["check", stale])
    assert rc == EXIT_DRIFT


def test_check_validates_links(doc: str) -> None:
    rc = run(["check", doc, "--validate-links"])
    assert rc == EXIT_DRIFT  # no block -> fresh entries always valid? verify below


def test_check_json_report(doc: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(["generate", doc])
    rc = run(["check", doc, "--json"])
    assert rc == EXIT_SUCCESS
    report = json.loads(capsys.readouterr().out)
    assert report["files"][0]["drifted"] is False


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------


def test_no_command_is_input_error() -> None:
    rc = run([])
    assert rc == EXIT_INPUT


def test_unknown_command_is_input_error() -> None:
    rc = run(["bogus"])
    assert rc == EXIT_INPUT


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["--version"])
    assert rc == EXIT_SUCCESS
    assert "1.0.0" in capsys.readouterr().out
