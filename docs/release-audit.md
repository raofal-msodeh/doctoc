# Release audit — v1.0.0

**Date:** 2026-08-16
**Version:** 1.0.0
**Auditor:** Manus AI

## Gate results

| Gate | Command | Result |
|---|---|---|
| Linting | `ruff check src/doctoc tests` | All checks passed (E, W, F, I, UP, N, B, A, C4, SIM, TCH, ARG, PTH, RUF) |
| Formatting | `ruff format --check src/doctoc tests` | 10 files already formatted |
| Type checking | `mypy --strict src/doctoc` | Success: no issues found in 6 source files |
| Tests | `python3 -m pytest -q` | 84 passed |
| Red-team | `bash scripts/red_team.sh` | 20 passed, 0 failed |
| Build | `python3 -m build` | `doctoc-1.0.0.tar.gz` + `doctoc-1.0.0-py3-none-any.whl` built |
| Smoke test | `make example` | generate → drifted=1 then check → drifted=0 (idempotent) |

## What ships in v1.0.0

- `generate` and `check` subcommands with the four-value exit code contract.
- GitHub-identical slugification: accents, CJK, emoji, deduplication suffixes, inline-format stripping.
- ATX and Setext headings; headings inside fences and HTML comments excluded.
- `{#manual-id}` custom anchor overrides.
- `--validate-links` catching stale TOC entries against real headings.
- `--json` structured reporting; `--dry-run` drift computation without writes.
- Security gate in path resolution: traversal, symlink escape, cycles, null bytes, 32 MiB file cap.
- Public Python API: `doctoc.generate()` / `doctoc.check()`.

## Known limitations

- Only UTF-8 files are supported (non-UTF-8 files are rejected with an input error).
- Markdown tables and reference-style link definitions are not headings and are ignored as intended.
- The tool is local-only by design; no network features exist or are planned for 1.x.

## Notes

- CI workflow token in this environment lacks push permissions; the workflow file is provided for users to self-host (`docs/ci-workflow.md`).
- All 20 red-team scenarios are deterministic and run in a temporary directory with no filesystem side effects.
