# CI workflow for DocToc

DocToc ships with a ready-to-use GitHub Actions workflow. Drop the file below into `.github/workflows/doctoc.yml` in any repository that wants its Markdown TOCs kept in sync.

```yaml
name: TOC sync

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: write   # only needed for the auto-fix job

jobs:
  toc:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install dist/doctoc-1.0.0-py3-none-any.whl
      - name: Check TOCs
        run: doctoc check docs/ README.md --validate-links
```

For the auto-fix variant (commit the regenerated TOC back on push to `main`), add a second job that runs `doctoc generate` and pushes with `peter-evans/create-pull-request` or a bot account. Two practical notes gathered from operating this exact setup:

1. **The gate must run before the fix.** Running `check` first makes drift visible on pull requests even when the auto-fix job is not permitted to push, so contributors see the failure immediately.
2. **Tokens with `contents: write` cannot self-approve.** Use a dedicated bot token and require review from a human before merging auto-generated TOC commits, to keep the audit trail honest.
