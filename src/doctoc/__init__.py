"""
DocToc: generate and sync GitHub-compatible tables of contents.

Public API:

.. code-block:: python

    from doctoc import generate, check

    results = generate(["README.md"])
    if any(r.drifted for r in results):
        print("TOC was updated")

    status = check(["docs/"], validate_links=True)
    assert status == 0, "TOC drift detected in CI"
"""

from __future__ import annotations

from .engine import (
    TocOptions,
    TocResult,
    process_paths,
)

__version__ = "1.0.0"
__all__ = [
    "TocOptions",
    "TocResult",
    "check",
    "generate",
]


def generate(
    paths: list[str],
    options: TocOptions | None = None,
    validate_links: bool = False,
) -> list[TocResult]:
    """Generate or update TOC blocks in the given files/directories."""
    opts = options or TocOptions(validate_links=validate_links)
    return process_paths(paths, opts, check_only=False)


def check(
    paths: list[str],
    options: TocOptions | None = None,
    validate_links: bool = False,
) -> int:
    """Check for TOC drift without modifying files. Returns 0 when clean."""
    opts = options or TocOptions(validate_links=validate_links)
    results = process_paths(paths, opts, check_only=True)
    if any(r.drifted for r in results) or any(r.link_errors for r in results):
        return 1
    return 0
