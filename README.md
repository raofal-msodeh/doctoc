# DocToc
<!--TOC-->
  - [Quick start](quick-start)
  - [Commands](commands)
    - [generate](generate)
    - [check](check)
    - [Exit codes](exit-codes)
  - [Features](features)
  - [Python API](python-api)
  - [Project structure](project-structure)
  - [Development](development)
  - [Security](security)
  - [License](license)
  - [Related tools](related-tools)
<!--/TOC-->
**Generate and sync GitHub-compatible tables of contents for Markdown files.**

DocToc is a small, dependency-free command-line tool (and importable Python library) that generates, synchronizes, and checks tables of contents (TOCs) for Markdown documents. It reproduces the [GitHub anchor slugification algorithm](https://github.com/jch/html-pipeline/blob/master/lib/html/pipeline/toc_filter.rb) so that the links it emits are byte-for-byte compatible with GitHub's rendered heading anchors, and it exposes a `check` subcommand designed to be used as a CI gate that fails the build whenever a TOC block has drifted out of date.

| Badge | Status |
|---|---|
| Python | 3.11, 3.12, 3.13 |
| Dependencies | Zero runtime dependencies |
| License | MIT |
| Quality | `ruff` (E, W, F, I, UP, N, B, A, C4, SIM, TCH, ARG, PTH, RUF), `mypy --strict`, `pytest`, red-team (20/20) |

## Quick start

Install from PyPI-style wheel or the repository:

```bash
pip install dist/doctoc-1.0.0-py3-none-any.whl
```

Mark the insertion point in any Markdown file with a TOC block, then run the generator:

```bash
printf '# My Project\n\n## Usage\n\n### Options\n\n## Roadmap\n' > doc.md
printf '<!--TOC-->\n<!--/TOC-->\n' > toc.md
doctoc generate doc.md toc.md
```

The file is rewritten so that everything between `<!--TOC-->` and `<!--/TOC-->` becomes an up-to-date ordered list of anchor links:

```markdown
<!--TOC-->
  - [My Project](my-project)
    - [Usage](usage)
      - [Options](options)
  - [Roadmap](roadmap)
<!--/TOC-->
```

Running `generate` again is idempotent: when the TOC is already current the file is left untouched.

## Commands

### `generate`

Rewrite the TOC block in every Markdown file matched by the given paths (files and directories). If a file has no TOC block, one is appended after the first heading.

| Option | Default | Meaning |
|---|---|---|
| `--max-depth LEVEL` | `6` | Skip headings deeper than `LEVEL` (1–6) |
| `--first-h1` | off | Include the document's first H1 (title) in the TOC |
| `--indent STR` | two spaces | Indentation string per nesting level |
| `--validate-links` | off | Fail when a TOC entry links to no unique heading |
| `--json` | off | Emit a machine-readable JSON report to stdout |
| `--dry-run` | off | Compute drift without writing anything |

### `check`

The same pipeline as `generate`, but non-destructive: it never touches the files and exits with code `1` if any TOC has drifted or any link is invalid. This makes it a natural CI gate:

```yaml
- name: TOC drift gate
  run: doctoc check docs/ --validate-links
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success: every TOC up to date, all links valid |
| `1` | At least one TOC drifted or a link is invalid (`check` / `--validate-links`) |
| `2` | Caller input error (bad path, bad option, non-UTF-8 file) |
| `3` | Internal engine error |

## Features

**GitHub-identical slugs.** Headings are slugified exactly the way GitHub does: lowercased, stripped of everything outside `[\w\- ]`, accents decomposed (Café → `café`), duplicate anchors suffixed `-1`, `-2`, …, and inline Markdown formatting (`**bold**`, `[link](…)`, `<em>`) removed from the visible TOC text.

**Setext and ATX headings.** Both `## ATX` and `Setext\n---` style headings are extracted, inside or outside of fenced code blocks and HTML comments (headings *inside* those are correctly ignored).

**Custom anchor overrides.** GitHub lets you pin an anchor with `{#manual-id}`; DocToc honours the same syntax.

**Link validation.** `--validate-links` walks every entry in the *existing* TOC block and fails when an entry has no unique matching heading — catching stale links left behind after a rename.

**Security by default.** Path traversal (`../`), symlinks escaping the working directory, symlink cycles deeper than 64 hops, null bytes, and absurdly large files (>32 MiB) are all rejected before any content is read. The tool never touches the network and never writes outside the paths you explicitly pass.

**Deterministic output.** Anchors are recomputed from scratch on every run with a fresh slugger, so the generated TOC is identical regardless of the file's previous state.

## Python API

```python
from doctoc import generate, check, TocOptions

results = generate(["README.md"], options=TocOptions(first_h1=True))
if any(r.drifted for r in results):
    print("TOC was updated")

status = check(["docs/"], validate_links=True)
assert status == 0, "TOC drift detected in CI"
```

`generate()` returns a list of `TocResult` objects (`path`, `entries`, `drifted`, `link_errors`); `check()` returns `0` for clean and `1` for drift or invalid links, mirroring the CLI exit codes.

## Project structure

```text
src/doctoc/
├── __init__.py     # public API: generate() / check()
├── __main__.py     # python -m doctoc entry point
├── cli.py          # argparse CLI, exit-code contract
├── engine.py       # file I/O, path resolution, TOC sync
├── errors.py       # TocInputError / TocEngineError hierarchy
└── toc.py          # heading extraction + GitHub slug algorithm
tests/              # 84 unit/integration tests
scripts/red_team.sh # 20 adversarial scenarios
docs/               # architecture, ADRs, release audit
```

## Development

```bash
make install     # editable install
make quality     # ruff + mypy --strict
make test        # pytest
make redteam     # 20 adversarial scenarios
make build       # sdist + wheel
make example     # end-to-end smoke test
```

## Security

See [SECURITY.md](SECURITY.md). In short: report vulnerabilities privately, and note that DocToc is a local-only tool that never transmits data externally. Adversarial inputs (path traversal, symlink escapes, null bytes, huge files, broken encodings) are covered by `scripts/red_team.sh`.

## License

MIT — see [LICENSE](LICENSE).

## Related tools

- [github/markdown-toc](https://github.com/ariatemplates/markdown-toc) — the Node.js original this tool's slug algorithm is modelled on
- [techknowlogick/xurls](https://github.com/techknowlogick/xurls) — unrelated, but often bundled with TOC tooling in docs generators
- GitHub's own [Table of Contents extension](https://github.com/derlin/bitdowntoc) — a GUI alternative; DocToc targets CI automation
