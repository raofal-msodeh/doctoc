# Contributing to DocToc

Thank you for considering a contribution. DocToc is intentionally small, and that is deliberate: every new feature competes with simplicity, so please open an issue before starting work on anything larger than a bug fix.

## Getting started

```bash
make install   # editable install
make quality   # ruff check + ruff format + mypy --strict
make test      # pytest (all 84 tests must pass)
make redteam   # 20 adversarial scenarios must pass
make build     # sdist + wheel
```

A change is considered complete when `make quality`, `make test`, and `make redteam` all pass with zero failures.

## Code style

The repository enforces strict linting and typing:

- **ruff** with `E, W, F, I, UP, N, B, A, C4, SIM, TCH, ARG, PTH, RUF` selected and the formatter active (line length 99).
- **mypy** in `--strict` mode for the entire `src/doctoc` package.
- New tests are expected for new behaviour, and bug fixes must ship a reproducer test.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Add or update tests so behaviour is pinned down.
3. Run `make quality test redteam build` locally and confirm everything passes.
4. Open the PR with a description of *why* the change is needed, not just *what* changed.

## Scope guidance

In scope: anchor correctness against GitHub's rendering, CI gate reliability, performance on large documents, and documentation. Out of scope: network features, templating beyond the `<!--TOC-->…<!--/TOC-->` markers, and Markdown extensions that GitHub itself does not render.

## Security issues

See [SECURITY.md](SECURITY.md) — report vulnerabilities privately, never through a public issue.
