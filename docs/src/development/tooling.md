# Developer tooling

The repository uses mise to provide project tools and named tasks. Install mise, then run:

```bash
mise install --locked
```

Use the same commands locally and in automation:

```bash
mise run check
mise run fix
mise run docs:check
mise run docs:build
mise run docs:deployment:enable
mise run docs:serve
```

`check` is read-only. `fix` changes the working tree. Contextlint checks links, anchors, and image targets across README
and `docs/**/*.md`. The pre-commit hook may fix files while safely stashing unrelated unstaged work. The commit-message
hook enforces Conventional Commits, required scopes for changelog-visible changes, grammar, 72/100-character line
limits, and canonical optional `Beads:` footers. Harper applies its full native rule set to human-authored text after
filtering Git comments/diffs, canonical release subjects, and the canonical machine-readable footer. Run `cog changelog`
to preview the concise user-facing changelog. The hk policy uses native built-in steps whenever their behavior matches;
hk's file locking coordinates independent steps. No dependency chain serializes unrelated checks.

## Python

Ruff lint and formatting plus ty type checking run on Python files in check, fix, and pre-commit. When root
`pyproject.toml` and `tests/**/*.py` both exist, `mise run check` also runs `uv run pytest`. Pytest must be declared by
the project; setup does not add or download it.

## GitHub validation

`.github/workflows/validate.yml` runs on every push and pull request. It isolates user-global mise configuration,
installs only the committed lock with `mise install --locked`, and runs `mise run check`. CI does not regenerate the
lock or maintain a separate validation policy.

## Hooks and recovery

Setup installs repository-local hk hooks when the destination is a Git repository. To restore tooling after an offline
or degraded setup, run:

```bash
python3 scripts/setup-tooling.py --json
```

The command preserves the scaffold when resolution, installation, or hook setup fails and reports the failed stage and
recovery commands. A repository created without Git can install hooks after Git initialization with:

```bash
python3 scripts/setup-tooling.py --json
```
