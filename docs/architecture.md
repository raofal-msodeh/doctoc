# DocToc Architecture

DocToc is organized as three concentric layers: a pure-algorithm core, an engine that performs I/O around that core, and a CLI that translates command-line arguments into engine calls. Each layer has a single reason to change, and dependencies flow strictly inward — the core knows nothing about files, and the engine knows nothing about arguments.

## Layer map

| Layer | Module | Responsibility |
|---|---|---|
| Core | `src/doctoc/toc.py` | Heading extraction and GitHub slugification |
| Engine | `src/doctoc/engine.py` | Path resolution, file I/O, TOC sync and validation |
| CLI | `src/doctoc/cli.py` | Argument parsing, exit-code contract, JSON reporting |
| API | `src/doctoc/__init__.py` | Thin `generate()` / `check()` wrappers over the engine |
| Errors | `src/doctoc/errors.py` | `TocInputError` (caller fault) vs `TocEngineError` (runtime fault) |

## The core (`toc.py`)

`toc.py` is a dependency-free module whose two public surfaces are `extract_headings(source)` and `github_slug(slugger, text)`. Heading extraction is a single linear scan that tracks two pieces of context: whether the scanner is currently inside a fenced code block (```` or `~~~` openers, matched closers) and whether it is inside an HTML comment (`<!-- … -->`, possibly multi-line). A line qualifies as a heading only when it is an ATX heading (`^#{1,6} `) or a Setext underline (`---` / `===`) *and* the scanner is in plain document context. Explicit anchor overrides written as `{#manual-id}` are parsed and carried on the resulting `Heading` object.

Slugification follows the algorithm published in GitHub's [html-pipeline TOC filter](https://github.com/jch/html-pipeline/blob/master/lib/html/pipeline/toc_filter.rb): strip inline Markdown formatting, lowercase, normalize Unicode (NFD decomposition removes combining accents such as Café → `cafe`), drop everything outside `[\w\- ]`, trim, and collapse runs of spaces to single hyphens. A stateful `_Slugger` deduplicates anchors with `-1`, `-2`, … suffixes in document order, which is what makes repeated `generate` runs idempotent.

## The engine (`engine.py`)

The engine's entry point, `process_paths`, first runs every caller-supplied path through `resolve_paths`, a security gate that refuses relative `..` traversal, symlinks that resolve outside the working directory, symlink chains deeper than 64 hops, null bytes, and files larger than 32 MiB. Only after validation does it read content, and only UTF-8 is accepted (a clear input error is raised for broken encodings).

`process_file` is the heart of the tool. It extracts headings, recomputes anchors from scratch with a fresh slugger (guaranteeing deterministic output regardless of the file's previous state), filters by `max_depth` and `first_h1`, and renders the ordered list between `<!--TOC-->` and `<!--/TOC-->` markers. When `--validate-links` is active, every entry in the *existing* block is checked against the extracted headings before the block is rewritten, so a renamed heading that left a stale link behind fails the command. Drift detection compares the freshly rendered block against the existing one character by character; files are rewritten only when they actually drifted.

## The CLI (`cli.py`)

The CLI is deliberately thin: `_build_parser` defines two subcommands (`generate`, `check`) sharing a common option set, and `run()` maps outcomes to a four-value exit code contract (`0` success, `1` drift or invalid link, `2` caller input error, `3` internal engine error). This contract is what lets `doctoc check` act as a CI gate: pipelines can distinguish "something is wrong with my arguments" from "the TOC needs resyncing" without parsing stdout. With `--json`, a structured report is emitted to stdout while human-readable summaries go to stderr, so the two channels never contaminate each other.

## Error model

Two exception families carry the distinction through every layer. `TocInputError` means the caller supplied something invalid — a missing file, a traversal attempt, a broken option — and always surfaces as exit code `2` with a message on stderr. `TocEngineError` means the environment failed after validation began — a disk error mid-write, permissions lost after open — and surfaces as exit code `3`. Anything the engine can foresee (encoding, size, traversal) is converted to input errors *before* content is read, which keeps the failure mode predictable and the tool safe to run on untrusted trees.

## Testing strategy

| Suite | Coverage |
|---|---|
| `tests/test_toc.py` | Slugification: accents, CJK, emoji, dedup, inline formatting, fence/comment exclusion, Setext, custom anchors |
| `tests/test_engine.py` | Path resolution security, drift detection, marker insertion, validation, binary/large files |
| `tests/test_cli.py` | Exit codes, option validation, dry-run, directory recursion, JSON output |
| `scripts/red_team.sh` | 20 adversarial scenarios (traversal, symlink escape, null bytes, huge docs, unclosed fences, empty files) |
