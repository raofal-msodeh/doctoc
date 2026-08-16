"""Tests for the TOC engine: generation, sync, drift detection, validation."""

from __future__ import annotations

import os
import tempfile

import pytest

from doctoc.engine import (
    TocOptions,
    process_file,
    process_paths,
    resolve_paths,
)
from doctoc.errors import TocInputError

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


# ---------------------------------------------------------------------------
# Block generation and idempotency
# ---------------------------------------------------------------------------


def test_generate_creates_block_after_first_h1(workdir: str) -> None:
    path = _write(
        workdir,
        "doc.md",
        "# Title\n\nIntro\n\n## Section\n",
    )
    result = process_file(path, TocOptions())
    assert result.drifted
    content = _read(path)
    # the block is inserted directly after the first H1 line
    assert content.startswith("# Title\n" + START)
    assert START in content and END in content
    toc = content.split(START)[1].split(END)[0]
    assert "- [Section](section)" in toc


def test_generate_top_insertion_without_h1(workdir: str) -> None:
    path = _write(workdir, "doc.md", "## Section only\n")
    result = process_file(path, TocOptions())
    assert result.drifted
    assert _read(path).startswith(START)


def test_generate_idempotent(workdir: str) -> None:
    path = _write(workdir, "doc.md", "# T\n\n## A\n\n## B\n")
    process_file(path, TocOptions())
    second = process_file(path, TocOptions())
    assert not second.drifted


def test_generate_updates_stale_block(workdir: str) -> None:
    path = _write(
        workdir,
        "doc.md",
        "# T\n\n<!--TOC-->\n- [Old](#old)\n<!--/TOC-->\n\n## New\n",
    )
    result = process_file(path, TocOptions())
    assert result.drifted
    content = _read(path)
    assert "- [New](new)" in content
    assert "- [Old](old)" not in content


def test_generate_removes_duplicate_entry(workdir: str) -> None:
    path = _write(
        workdir,
        "doc.md",
        "# T\n\n<!--TOC-->\n  - [A](#a)\n  - [A](#a)\n<!--/TOC-->\n\n## A\n",
    )
    result = process_file(path, TocOptions())
    assert result.drifted
    toc = _read(path).split(START)[1].split(END)[0]
    assert toc.strip().count("[A]") == 1


def test_check_only_never_writes(workdir: str) -> None:
    path = _write(
        workdir,
        "doc.md",
        "# T\n\n<!--TOC-->\n- [Stale](#stale)\n<!--/TOC-->\n\n## Real\n",
    )
    result = process_file(path, TocOptions(), check_only=True)
    assert result.drifted
    assert result.content is None  # nothing written in check mode
    assert "Stale" in _read(path)  # file untouched


def test_generate_result_carries_new_content(workdir: str) -> None:
    path = _write(workdir, "doc.md", "# T\n\n## S\n")
    result = process_file(path, TocOptions(), check_only=False)
    assert result.drifted
    assert result.content is not None
    assert START in result.content
    assert "- [S](s)" in result.content
    # source file updated in generate mode
    assert "- [S](s)" in _read(path)


def test_max_depth(workdir: str) -> None:
    path = _write(workdir, "doc.md", "# T\n\n## A\n\n### B\n\n#### C\n")
    result = process_file(path, TocOptions(max_depth=2))
    assert any(e.anchor == "a" for e in result.entries)
    assert not any(e.level > 2 for e in result.entries)


def test_first_h1_included(workdir: str) -> None:
    path = _write(workdir, "doc.md", "# Title\n\n## A\n")
    result = process_file(path, TocOptions(first_h1=True))
    assert any(e.anchor == "title" for e in result.entries)


def test_first_h1_excluded_by_default(workdir: str) -> None:
    path = _write(workdir, "doc.md", "# Title\n\n## A\n")
    result = process_file(path, TocOptions())
    assert not any(e.anchor == "title" for e in result.entries)


def test_custom_indent(workdir: str) -> None:
    path = _write(workdir, "doc.md", "# T\n\n## A\n\n### B\n")
    result = process_file(path, TocOptions(indent="    "))
    toc = result.content or ""
    assert "    - [B](b)" in toc


# ---------------------------------------------------------------------------
# Link validation
# ---------------------------------------------------------------------------


def test_validate_catches_stale_link(workdir: str) -> None:
    path = _write(
        workdir,
        "doc.md",
        "# T\n\n<!--TOC-->\n- [S](#stale)\n<!--/TOC-->\n\n## R\n",
    )
    result = process_file(path, TocOptions(validate_links=True), check_only=True)
    assert len(result.link_errors) == 1
    assert "stale" in result.link_errors[0]


def test_validate_first_duplicate_anchor_valid(workdir: str) -> None:
    # two identical headings get distinct anchors (a, a-1); linking the
    # first one is unambiguous and valid
    path = _write(
        workdir,
        "doc.md",
        "# T\n\n<!--TOC-->\n- [A](#a)\n- [A](#a-1)\n<!--/TOC-->\n\n## A\n\n## A\n",
    )
    result = process_file(path, TocOptions(validate_links=True), check_only=True)
    assert result.link_errors == []


def test_validate_catches_percent_encoded_link(workdir: str) -> None:
    path = _write(
        workdir,
        "doc.md",
        "# T\n\n<!--TOC-->\n- [X](#x%20y)\n<!--/TOC-->\n\n## X Y\n",
    )
    result = process_file(path, TocOptions(validate_links=True), check_only=True)
    # percent-encoded anchors do not match the computed plain anchors,
    # so hand-written links must use the plain slug form
    assert len(result.link_errors) == 1


# ---------------------------------------------------------------------------
# Path resolution security
# ---------------------------------------------------------------------------


def test_resolve_single_file(workdir: str) -> None:
    path = _write(workdir, "a.md", "# X\n")
    assert resolve_paths(["a.md"], base_dir=workdir) == [path]


def test_resolve_directory_picks_markdown(workdir: str) -> None:
    _write(workdir, "a.md", "# X\n")
    _write(workdir, "b.txt", "not markdown\n")
    sub = os.path.join(workdir, "sub")
    os.makedirs(sub)
    _write(sub, "c.markdown", "# Y\n")
    resolved = resolve_paths(["."], base_dir=workdir)
    names = sorted(os.path.basename(p) for p in resolved)
    assert names == ["a.md", "c.markdown"]


def test_resolve_rejects_escape_traversal(workdir: str) -> None:
    with pytest.raises(TocInputError):
        resolve_paths(["../secret.md"], base_dir=workdir)


def test_resolve_explicit_absolute_path_accepted(workdir: str) -> None:
    # an explicitly given absolute path to an existing file is honoured
    # (caller opt-in); symlinks escaping base are still refused
    target = os.path.join(workdir, "target.md")
    _write(workdir, "target.md", "# X\n")
    result = resolve_paths([target], base_dir=workdir)
    assert result == [os.path.normpath(target)]


def test_resolve_rejects_symlink_outside_base(workdir: str) -> None:
    target = os.path.join(os.path.dirname(workdir), "_doctoc_target")
    link = os.path.join(workdir, "escape_link")
    try:
        os.makedirs(target, exist_ok=True)
        os.symlink(target, link)
        with pytest.raises(TocInputError):
            resolve_paths(["escape_link"], base_dir=workdir)
    finally:
        os.unlink(link)
        os.rmdir(target)


def test_resolve_rejects_null_bytes(workdir: str) -> None:
    with pytest.raises(TocInputError):
        resolve_paths(["a\u0000.md"], base_dir=workdir)


def test_resolve_rejects_missing_file(workdir: str) -> None:
    with pytest.raises(TocInputError):
        resolve_paths(["missing.md"], base_dir=workdir)


def test_resolve_rejects_empty_argument(workdir: str) -> None:
    with pytest.raises(TocInputError):
        resolve_paths([""], base_dir=workdir)


def test_process_paths_no_matches(workdir: str) -> None:
    with pytest.raises(TocInputError):
        process_paths(["nonexistent"], TocOptions())


def test_binary_file_rejected(workdir: str) -> None:
    path = os.path.join(workdir, "bin.md")
    with open(path, "wb") as handle:
        handle.write(b"\x00\x01\x02")
    with pytest.raises(TocInputError):
        process_file(path, TocOptions())
