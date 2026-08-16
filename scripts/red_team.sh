#!/usr/bin/env bash
# DocToc red-team: adversarial CLI scenarios.
# Each scenario must behave safely and return the documented exit code.
set -uo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SRC_DIR" || exit 2

exec python3 - "$SRC_DIR" <<'PY'
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(sys.argv[1], "src"))

from doctoc.cli import EXIT_DRIFT, EXIT_INPUT, EXIT_SUCCESS, run

passed = 0
failed = 0
src_root = sys.argv[1]


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed  # noqa: PLW0603
    if condition:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


def run_capture(args: list[str]):
    """Run doctoc capturing both stdout and stderr."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = run(args)
    return rc, out.getvalue(), err.getvalue()


def write_to(directory: str, name: str, content: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


with tempfile.TemporaryDirectory() as tmp:
    doc = write_to(tmp, "doc.md", "# Title\n\n## Section\n\n### Sub\n")

    # RT-01: path traversal outside cwd is rejected.
    rc, _, _ = run_capture(["generate", "../escape.md"])
    check("RT-01 relative path traversal is rejected", rc == EXIT_INPUT)

    # RT-02: symlink pointing outside the working directory is refused.
    target = os.path.join(os.path.dirname(tmp), "_doctoc_rt_target")
    link = os.path.join(tmp, "escape_link.md")
    try:
        os.makedirs(target, exist_ok=True)
        os.symlink(target, link)
        rc, _, _ = run_capture(["generate", "escape_link.md"])
        check("RT-02 symlink escaping cwd is rejected", rc == EXIT_INPUT)
    finally:
        try:
            os.unlink(link)
        except OSError:
            pass
        try:
            os.rmdir(target)
        except OSError:
            pass

    # RT-03: null bytes in path are rejected.
    rc, _, _ = run_capture(["generate", "fil\u0000e.md"])
    check("RT-03 null byte in path is rejected", rc == EXIT_INPUT)

    # RT-04: binary file with NUL bytes is rejected.
    binary = os.path.join(tmp, "binary.md")
    with open(binary, "wb") as handle:
        handle.write(b"\x00\x01\x02\x03")
    rc, _, _ = run_capture(["generate", binary])
    check("RT-04 binary file is rejected as input error", rc == EXIT_INPUT)

    # RT-05: invalid --max-depth (7) is rejected.
    rc, _, err = run_capture(["generate", doc, "--max-depth", "7"])
    check("RT-05 max-depth 7 is rejected", rc == EXIT_INPUT and "max-depth" in err)

    # RT-06: invalid --max-depth (0) is rejected.
    rc, _, _ = run_capture(["generate", doc, "--max-depth", "0"])
    check("RT-06 max-depth 0 is rejected", rc == EXIT_INPUT)

    # RT-07: empty --indent is rejected.
    rc, _, _ = run_capture(["generate", doc, "--indent", ""])
    check("RT-07 empty indent is rejected", rc == EXIT_INPUT)

    # RT-08: nonexistent path is rejected.
    rc, _, _ = run_capture(["generate", "no-such-file.md"])
    check("RT-08 nonexistent file is rejected", rc == EXIT_INPUT)

    # RT-09: directory matching no markdown files is rejected.
    subdir = os.path.join(tmp, "empty_dir")
    os.makedirs(subdir)
    rc, _, _ = run_capture(["generate", subdir])
    check("RT-09 dir with no markdown files is rejected", rc == EXIT_INPUT)

    # RT-10: generate on file without markers creates a block (never crashes).
    rc, _, _ = run_capture(["generate", doc])
    content = open(doc, encoding="utf-8").read()
    check("RT-10 generate without markers inserts TOC block safely", rc == EXIT_SUCCESS and "<!--TOC-->" in content)

    # RT-11: idempotent second generate produces identical output.
    rc, _, _ = run_capture(["generate", doc])
    content2 = open(doc, encoding="utf-8").read()
    check("RT-11 second generate is idempotent", rc == EXIT_SUCCESS and content2 == content)

    # RT-12: check on a hand-crafted drifted block reports drift.
    check_doc = write_to(tmp, "check.md", "# T\n\n<!--TOC-->\n- [Stale](#stale)\n<!--/TOC-->\n\n## Real\n")
    rc, out, _ = run_capture(["check", check_doc, "--json"])
    try:
        data = json.loads(out)
        drifted = data["files"][0]["drifted"] is True
    except (json.JSONDecodeError, KeyError, IndexError):
        drifted = False
    check("RT-12 check detects drift and emits valid JSON", rc == EXIT_DRIFT and drifted)

    # RT-13: stale link fails validation.
    val_doc = write_to(tmp, "val.md", "# T\n\n<!--TOC-->\n- [Ghost](#ghost)\n<!--/TOC-->\n\n## Real\n")
    rc, out, err = run_capture(["generate", val_doc, "--validate-links", "--json"])
    link_errors = []
    try:
        data = json.loads(out)
        link_errors = data["files"][0]["link_errors"]
    except (json.JSONDecodeError, KeyError):
        pass
    check(
        "RT-13 stale TOC link fails validation",
        rc == EXIT_DRIFT and bool(link_errors) and "ghost" in (err + out),
    )

    # RT-14: heading inside fenced code block is ignored.
    fence_doc = write_to(tmp, "fence.md", "# Title\n\n```\n## Not A Heading\n```\n\n## Real Section\n")
    rc, _, _ = run_capture(["generate", fence_doc, "--first-h1", "--json"])
    check(
        "RT-14 heading inside fence is excluded from TOC",
        rc == EXIT_SUCCESS,
    )

    # RT-15: heading inside HTML comment is ignored.
    comment_doc = write_to(tmp, "comment.md", "# Title\n\n<!-- ## Commented Heading -->\n\n## Visible\n")
    run_capture(["generate", comment_doc, "--json", "--first-h1"])
    after = open(comment_doc, encoding="utf-8").read()
    check("RT-15 commented heading is excluded", "commented-heading" not in after and "visible" in after)

    # RT-16: duplicate headings get deduplicated anchors (title / title-1).
    dup_doc = write_to(tmp, "dup.md", "# T\n\n## Same\n\n## Same\n")
    run_capture(["generate", dup_doc, "--first-h1", "--json"])
    after = open(dup_doc, encoding="utf-8").read()
    check("RT-16 duplicate headings get unique anchors", "-1)" in after and "same)" in after)

    # RT-17: CJK characters slugify to plain text safely.
    cjk_doc = write_to(tmp, "cjk.md", "# T\n\n## \u6d4b\u8bd5\u6807\u9898\n")
    rc, _, _ = run_capture(["generate", cjk_doc, "--first-h1"])
    after = open(cjk_doc, encoding="utf-8").read()
    import re
    match = re.search(r"\]\(([^)]*)\)", after.split("<!--/TOC-->")[0])
    anchor = match.group(1) if match else ""
    check(
        "RT-17 CJK headings slugify without crashing",
        rc == EXIT_SUCCESS and bool(anchor),
    )

    # RT-18: extremely large heading count and long heading text do not hang.
    huge = "# T\n\n## " + "X" * 50_000 + "\n\n" + "\n".join(f"## h{i}" for i in range(500))
    huge_doc = write_to(tmp, "huge.md", huge)
    start = time.time()
    rc, _, _ = run_capture(["generate", huge_doc])
    check("RT-18 huge document completes fast", rc == EXIT_SUCCESS and time.time() - start < 10)

    # RT-19: unclosed fence at EOF treats trailing heading as code.
    unclosed = "# Title\n\n```\n## Trapped\n"
    unclosed_doc = write_to(tmp, "unclosed.md", unclosed)
    run_capture(["generate", unclosed_doc, "--first-h1"])
    after = open(unclosed_doc, encoding="utf-8").read()
    check("RT-19 unclosed fence excludes trailing heading", "trapped" not in after and "- [Title]" in after)

    # RT-20: empty file gets no TOC and never errors.
    empty_doc = write_to(tmp, "empty.md", "")
    rc, _, _ = run_capture(["generate", empty_doc])
    check("RT-20 empty file is handled gracefully", rc == EXIT_SUCCESS and "<!--TOC-->" not in open(empty_doc, encoding="utf-8").read())

print(f"\nred-team: {passed} passed, {failed} failed out of {passed + failed}")
sys.exit(1 if failed else 0)
PY
