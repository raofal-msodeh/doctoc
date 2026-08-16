"""
TOC generation and sync engine: markers, rendering, and drift checking.

DocToc stores generated tables of contents between comment markers:

    <!--TOC-->
    - [Section](#section)
      - [Sub-section](#sub-section)
    <!--/TOC-->

Design rules:

* ``generate`` creates or updates the block; without markers the block
  is inserted after the first heading (H1) or at the top of the file.
* ``check`` never modifies files and returns a structured report so CI
  can ``set -e`` on drift.
* ``--validate-links`` verifies every TOC link resolves to an existing
  heading anchor, catching duplicates and misspellings.
* TOC entry text mirrors GitHub's rendering: formatting stripped.
"""

from __future__ import annotations

import dataclasses
import os
import re
from pathlib import Path

from .errors import TocEngineError, TocInputError
from .toc import (
    Heading,
    _Slugger,
    extract_headings,
    github_slug,
    plain_text,
)

DEFAULT_START = "<!--TOC-->"
DEFAULT_END = "<!--/TOC-->"
MAX_FILE_BYTES = 32 * 1024 * 1024  # refuse absurdly large files
MAX_DEPTH = 64  # symlink / directory depth safety limit

BLOCK_RE = re.compile(r"^(\s*)<!--TOC-->\n(.*?)<!--/TOC-->\s*\n?", re.DOTALL | re.MULTILINE)


@dataclasses.dataclass(frozen=True)
class TocOptions:
    """Options controlling TOC generation."""

    start_marker: str = DEFAULT_START
    end_marker: str = DEFAULT_END
    max_depth: int | None = None  # max heading level (None = 6)
    validate_links: bool = False
    first_h1: bool = False  # False skips the document's first H1 (title)
    indent: str = "  "  # two spaces per level


@dataclasses.dataclass(frozen=True)
class TocEntry:
    """One entry in a rendered table of contents."""

    level: int
    text: str
    anchor: str
    target_line: int  # 0 when the link could not be resolved


@dataclasses.dataclass(frozen=True)
class TocResult:
    """Structured result of generating or checking a TOC."""

    path: str
    entries: list[TocEntry]
    drifted: bool
    link_errors: list[str]
    content: str | None = None  # new file content when ``drifted`` in generate


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="strict") as handle:
            content = handle.read()
    except UnicodeDecodeError as exc:
        raise TocInputError(f"{path}: not valid UTF-8") from exc
    except OSError as exc:
        raise TocInputError(f"{path}: {exc}") from exc
    if "\x00" in content:
        raise TocInputError(f"{path}: binary file (contains null bytes)")
    return content


def _write_file(path: str, content: str) -> None:
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise TocEngineError(f"{path}: write failed: {exc}") from exc


def resolve_paths(paths: list[str], base_dir: str | None = None) -> list[str]:
    """
    Resolve and validate input paths (files and directories).

    Refuses absolute ``..`` traversal outside the base directory and
    symlinks deeper than ``MAX_DEPTH``.
    """
    base = str((Path.cwd() if not base_dir else Path(base_dir)).resolve())
    resolved: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not raw:
            raise TocInputError("empty path argument")
        _check_depth(raw)
        try:
            parts = Path(raw).parts
        except ValueError as exc:
            raise TocInputError(f"{raw}: {exc}") from exc
        if raw.startswith("..") or ".." in parts:
            raise TocInputError(f"{raw}: relative path escapes cwd")
        if Path(raw).is_absolute():
            candidate = str(Path(raw).resolve())
        else:
            candidate = str((Path(base) / raw).resolve())
        candidate_path = Path(candidate)
        if candidate_path.exists():
            if candidate_path.is_symlink():
                real_candidate = str(candidate_path.resolve())
                if not real_candidate.startswith(base + os.sep) and real_candidate != base:
                    raise TocInputError(f"{raw}: symlink escapes the working directory")
        if not candidate_path.exists():
            raise TocInputError(f"{raw}: no such file or directory")
        if candidate_path.is_symlink() and _symlink_depth(raw) > MAX_DEPTH:
            raise TocInputError(f"{raw}: too many symlink hops")
        if candidate_path.is_file():
            _check_size(candidate)
            if candidate not in seen:
                seen.add(candidate)
                resolved.append(candidate)
            continue
        if candidate_path.is_dir():
            for dirpath, dirnames, filenames in os.walk(candidate_path):
                dirnames.sort()
                for name in sorted(filenames):
                    if name.lower().endswith(".md") or name.lower().endswith(".markdown"):
                        full = str(Path(dirpath) / name)
                        if full not in seen:
                            _check_size(full)
                            seen.add(full)
                            resolved.append(full)
            continue
        raise TocInputError(f"{raw}: not a regular file or directory")
    if not resolved:
        raise TocInputError("no Markdown files matched the given paths")
    return resolved


def _check_size(path: str) -> None:
    try:
        size = Path(path).stat().st_size
    except OSError as exc:
        raise TocInputError(f"{path}: {exc}") from exc
    if size > MAX_FILE_BYTES:
        raise TocInputError(f"{path}: file larger than {MAX_FILE_BYTES} bytes")


def _symlink_depth(path: str) -> int:
    depth = 0
    current = Path(path)
    while current.is_symlink():
        depth += 1
        if depth > MAX_DEPTH:
            return depth
        current = current.parent / current.readlink()
    return depth


def _check_depth(_path: str) -> None:
    """Validate path components (no NUL bytes)."""
    if "\0" in _path:
        raise TocInputError("path contains null bytes")


def _render_entries(headings: list[Heading], options: TocOptions) -> list[TocEntry]:
    """Render headings into TOC entries applying filters."""
    entries: list[TocEntry] = []
    first_h1_skipped = False
    depth = options.max_depth if options.max_depth is not None else 6
    for heading in headings:
        if heading.level > depth:
            continue
        if not options.first_h1 and heading.level == 1 and not first_h1_skipped:
            first_h1_skipped = True
            continue
        entries.append(
            TocEntry(
                level=heading.level,
                text=heading.text,
                anchor=heading.anchor,
                target_line=heading.line,
            )
        )
    return entries


def _render_block(entries: list[TocEntry], options: TocOptions) -> str:
    lines: list[str] = []
    for entry in entries:
        indent = options.indent * (entry.level - 1)
        anchor = entry.anchor.replace(" ", "%20")
        link = f"[{plain_text(entry.text)}]({anchor})"
        lines.append(f"{indent}- {link}")
    inner = "\n".join(lines)
    return f"{options.start_marker}\n{inner}\n{options.end_marker}\n"


TOC_LINK = re.compile(r"^-\s+\[([^\]]*)\]\(#?([^)]*)\)")


def _existing_toc_links(source: str) -> list[tuple[str, str]]:
    """Extract (label, anchor) pairs from the TOC block already in source."""
    existing = _existing_block(source)
    if existing is None:
        return []
    block_content = existing[1]
    links: list[tuple[str, str]] = []
    for line in block_content.splitlines():
        match = TOC_LINK.match(line.strip())
        if match is not None:
            links.append((match.group(1), match.group(2)))
    return links


def _validate(entries: list[TocEntry], source: str) -> list[str]:
    """
    Verify every TOC link resolves to a unique heading anchor.

    Validates links that actually appear in the file's existing TOC
    block (so stale or misspelled links are caught) plus, when no block
    exists, the freshly generated entries.
    """
    all_anchors: list[str] = [heading.anchor for heading in extract_headings(source)]
    links = _existing_toc_links(source) or [(entry.text, entry.anchor) for entry in entries]
    errors: list[str] = []
    for label, anchor in links:
        count = all_anchors.count(anchor)
        if count == 0:
            errors.append(f'link #{anchor} (label "{label}") matches no heading')
        elif count > 1:
            errors.append(
                f'link #{anchor} (label "{label}") is ambiguous ({count} duplicate headings)'
            )
    return errors


def _existing_block(source: str) -> tuple[str, str, str] | None:
    """Return (prefix, block_content, suffix) if a TOC block exists."""
    match = BLOCK_RE.search(source)
    if match is None:
        return None
    return match.group(1), match.group(2), source[match.end() :]


def process_file(path: str, options: TocOptions, check_only: bool = False) -> TocResult:
    """
    Generate, sync, or check the TOC block of a single Markdown file.

    When ``check_only`` is False the file is rewritten when the TOC
    drifted; when True the file is never touched.
    """
    source = _read_file(path)
    headings = extract_headings(source)
    # recompute anchors with a fresh slugger for deterministic output
    if not headings:
        return TocResult(path=path, entries=[], drifted=False, link_errors=[])
    # headings already carry anchors computed in document order;
    # recompute from scratch to guarantee idempotent output
    recomputed: list[Heading] = []
    slugger = _Slugger()
    for heading in headings:
        if heading.anchor == github_slug(slugger, heading.text):
            recomputed.append(heading)
        else:
            recomputed.append(
                dataclasses.replace(heading, anchor=github_slug(slugger, heading.text))
            )
    entries = _render_entries(recomputed, options)
    link_errors = _validate(entries, source) if options.validate_links else []
    expected_block = _render_block(entries, options)
    existing = _existing_block(source)

    if existing is None:
        drifted = True
        after = _find_insertion_point(source)
        new_source = source[:after] + expected_block + source[after:]
    else:
        prefix, block_content, suffix = existing
        current_block = f"{prefix}{options.start_marker}\n{block_content}{options.end_marker}\n"
        drifted = current_block != expected_block
        new_source = source[: BLOCK_RE.search(source).start()] + expected_block + suffix  # type: ignore[union-attr]

    result = TocResult(
        path=path,
        entries=entries,
        drifted=drifted,
        link_errors=link_errors,
        content=new_source if drifted and not check_only else None,
    )
    if drifted and not check_only and result.content is not None:
        _write_file(path, result.content)
    return result


def _find_insertion_point(source: str) -> int:
    """
    Find the line index where a new TOC block should be inserted.

    Inserts after the first H1 heading (document title) when present,
    otherwise at the very top of the file.
    """
    lines = source.splitlines(keepends=True)
    first_h1 = next(
        (index for index, line in enumerate(lines) if re.match(r"^\s{0,3}#\s+", line)),
        None,
    )
    if first_h1 is not None:
        end_of_h1 = (
            lines[first_h1].index("\n") + 1 if "\n" in lines[first_h1] else len(lines[first_h1])
        )
        return end_of_h1
    return 0


def process_paths(
    paths: list[str], options: TocOptions, check_only: bool = False
) -> list[TocResult]:
    """Process every Markdown file matched by ``paths``."""
    results: list[TocResult] = []
    for path in resolve_paths(paths):
        results.append(process_file(path, options, check_only=check_only))
    return results
