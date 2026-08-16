"""
DocToc CLI: generate, sync, and check Markdown tables of contents.

Exit codes:

* ``0`` -- success; every TOC up to date (``check``) or files synced
  (``generate``).
* ``1`` -- at least one file drifted (``check`` only) or link
  validation failed.
* ``2`` -- caller input error (bad path, bad options, non-UTF-8 file).
* ``3`` -- internal engine error (disk full, permissions after open).
"""

from __future__ import annotations

import argparse
import json
import sys

from .engine import (
    TocOptions,
    TocResult,
    process_paths,
)
from .errors import DocTocError, TocInputError

EXIT_SUCCESS = 0
EXIT_DRIFT = 1
EXIT_INPUT = 2
EXIT_INTERNAL = 3

EXIT_CODES = {
    0: "success",
    1: "toc-drift-or-invalid-links",
    2: "input-error",
    3: "internal-error",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doctoc",
        description=("Generate and sync GitHub-compatible tables of contents for Markdown files."),
    )
    parser.add_argument("--version", action="version", version="doctoc 1.0.0")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser(
        "generate",
        help="generate or update TOC blocks in Markdown files",
        description=(
            "Rewrite TOC blocks between <!--TOC--> and <!--/TOC--> "
            "markers (creates a block when missing)."
        ),
    )
    gen.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="files or directories to process",
    )
    gen.add_argument(
        "--max-depth",
        type=int,
        default=None,
        metavar="LEVEL",
        help="skip headings deeper than LEVEL (1-6)",
    )
    gen.add_argument(
        "--first-h1",
        action="store_true",
        help="include the document's first H1 (title) in the TOC",
    )
    gen.add_argument(
        "--indent",
        default="  ",
        help="indent string per level (default: two spaces)",
    )
    gen.add_argument(
        "--validate-links",
        action="store_true",
        help="fail when a TOC link matches no unique heading anchor",
    )
    gen.add_argument(
        "--json",
        action="store_true",
        help="emit a JSON report to stdout",
    )
    gen.add_argument(
        "--dry-run",
        action="store_true",
        help="compute the TOC without writing files",
    )

    chk = sub.add_parser(
        "check",
        help="verify all TOC blocks are up to date without writing",
        description=(
            "Non-destructive CI gate: exits 1 when any TOC drifted or links are invalid."
        ),
    )
    chk.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="files or directories to check",
    )
    chk.add_argument(
        "--max-depth",
        type=int,
        default=None,
        metavar="LEVEL",
        help="skip headings deeper than LEVEL (1-6)",
    )
    chk.add_argument(
        "--first-h1",
        action="store_true",
        help="include the document's first H1 (title) in the TOC",
    )
    chk.add_argument(
        "--indent",
        default="  ",
        help="indent string per level (default: two spaces)",
    )
    chk.add_argument(
        "--validate-links",
        action="store_true",
        help="fail when a TOC link matches no unique heading anchor",
    )
    chk.add_argument(
        "--json",
        action="store_true",
        help="emit a JSON report to stdout",
    )
    return parser


def _report(results: list[TocResult]) -> dict[str, object]:
    files: list[dict[str, object]] = [
        {
            "path": result.path,
            "entries": len(result.entries),
            "drifted": result.drifted,
            "link_errors": result.link_errors,
        }
        for result in results
    ]
    return {"version": "1.0.0", "files": files}


def _summary(results: list[TocResult]) -> str:
    files = len(results)
    drifted = sum(1 for r in results if r.drifted)
    errors = sum(len(r.link_errors) for r in results)
    return f"{files} file(s), {drifted} with drifted TOC, {errors} link error(s)"


def run(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_INPUT if exc.code != 0 else EXIT_SUCCESS

    try:
        if getattr(args, "max_depth", None) is not None:
            if not 1 <= args.max_depth <= 6:
                raise TocInputError(f"--max-depth must be between 1 and 6 (got {args.max_depth})")
        if getattr(args, "indent", "") == "":
            raise TocInputError("--indent must not be empty")
        options = TocOptions(
            max_depth=args.max_depth,
            first_h1=args.first_h1,
            indent=args.indent,
            validate_links=args.validate_links,
        )
    except (ValueError, TocInputError) as exc:
        print(f"doctoc: {exc}", file=sys.stderr)
        return EXIT_INPUT

    check_only = args.command == "check" or getattr(args, "dry_run", False)
    try:
        results = process_paths(args.paths, options, check_only=check_only)
    except TocInputError as exc:
        print(f"doctoc: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except DocTocError as exc:
        print(f"doctoc: internal error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL

    if args.json:
        json.dump(_report(results), sys.stdout, indent=2, ensure_ascii=False)
        print()

    print(_summary(results), file=sys.stderr)

    if check_only:
        if any(r.drifted for r in results) or any(r.link_errors for r in results):
            return EXIT_DRIFT
        return EXIT_SUCCESS

    if any(r.link_errors for r in results):
        for result in results:
            for error in result.link_errors:
                print(f"doctoc: {result.path}: {error}", file=sys.stderr)
        return EXIT_DRIFT

    return EXIT_SUCCESS


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
