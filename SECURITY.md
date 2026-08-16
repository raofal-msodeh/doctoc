# Security Policy

## Reporting a vulnerability

Please report security issues privately by email or a private advisory before opening a public issue. This gives us time to verify and patch the problem without exposing users to a known attack surface.

## Scope

DocToc is a **local-only** tool. It reads Markdown files from the paths you explicitly pass on the command line (or through the Python API) and rewrites only those files. It never transmits data over the network, never calls external services, and never evaluates Markdown content.

## Known boundaries

| Boundary | Behaviour |
|---|---|
| Path traversal | Relative paths containing `..` are rejected before any I/O |
| Symlink escapes | Symlinks resolving outside the working directory are refused |
| Symlink cycles | Chains deeper than 64 hops are rejected (no unbounded `realpath` loops) |
| Null bytes | Paths containing `\0` are rejected outright |
| File size | Files larger than 32 MiB are refused before content is read |
| Encoding | Non-UTF-8 files fail with a clear input error |
| Content trust | Headings inside fenced code blocks and HTML comments are never rendered into the TOC |

Twenty adversarial scenarios covering these boundaries are executed by `scripts/red_team.sh` on every quality run.

## House rules

Never commit tokens, keys, or credentials into this repository, and never process content you do not trust as anything more than inert text — DocToc treats every byte it reads as data, never as code.
