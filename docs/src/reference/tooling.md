# Tooling reference

## Files

| File                                | Contract                                                                    |
|-------------------------------------|-----------------------------------------------------------------------------|
| `mise.toml`                         | Declares project tools, environment, and named tasks.                       |
| `mise.lock`                         | Project-owned resolved downloads; commit it.                                |
| `hk.pkl`                            | Defines the shared check/fix/pre-commit step map.                           |
| `.config/rumdl.toml`                | Configures Markdown linting and deterministic fixes.                        |
| `.editorconfig`                     | Keeps editor output on UTF-8, LF, final newlines, and no trailing spaces.   |
| `_typos.toml`                       | Ignores hash-like identifiers while retaining typo checks elsewhere.        |
| `contextlint.config.json`           | Checks documentation links, anchors, and image targets.                     |
| `cog.toml`                          | Configures Conventional Commits and concise changelogs.                     |
| `.config/cog-changelog.tera`        | Renders plain Markdown changelogs without author noise.                     |
| `scripts/setup-tooling.py`          | Resolves the lock, installs tools, installs hooks, and returns JSON status. |
| `scripts/enable-docs-deployment.py` | Configures workflow-built Pages through external `gh`.                      |
| `.github/workflows/validate.yml`    | Runs locked `mise run check` on pushes and pull requests.                   |
| `.github/workflows/docs.yml`        | Builds gated docs from the default branch or manual dispatch.               |

## Tools

The universal tool set is hk `1.49.0`, Node `lts`, and the `latest` Cocogitto, Harper CLI, Contextlint, mdBook, uv,
rumdl, typos, and `npm:markdown-table-formatter` releases. Contextlint checks documentation links, anchors, and image
targets. Its reviewed low-download aube exception applies only to `@contextlint/cli`. Both hk Pkl imports use `1.49.0`.

Recorded language profiles: `python`.

## Commit messages and changelogs

Changelog-visible `feat`, `fix`, `perf`, and `refactor` commits require a semantic scope. The commit hook also checks
Conventional Commit syntax, grammar, a 72-character subject, 100-character body lines, and canonical optional `Beads:`
footers. Internal build, chore, CI, documentation, release, style, and test commits are omitted from `cog changelog`.
Breaking changes render as plain Markdown.

The generated `cog.toml` initially accepts any syntactically valid scope. To constrain scopes, add a `scopes = ["..."]`
allowlist, document each stable subsystem in README when present or on this page otherwise, and update `AGENTS.md` so
agents apply the same taxonomy. Run `cog check` after changing the allowlist.

### Python profile

| Step        | Check                                        | Fix           | Files                                                  |
|-------------|----------------------------------------------|---------------|--------------------------------------------------------|
| Ruff lint   | `ruff check --force-exclude`                 | add `--fix`   | `**/*.py`, `**/*.pyi`                                  |
| Ruff format | `ruff format --quiet --force-exclude --diff` | omit `--diff` | `**/*.py`, `**/*.pyi`                                  |
| ty          | `ty check`                                   | none          | `**/*.py`, `**/*.pyi`                                  |
| pytest      | `uv run pytest`                              | none          | root `pyproject.toml` plus `tests/**/*.py`; check only |

Ruff and ty are mise-managed at `latest`; pytest is project-owned. The profile ignores `.venv/`, `__pycache__/`,
`*.py[cod]`, `.pytest_cache/`, and `.ruff_cache/`.

## Tasks

| Task                     | Behavior                                                              |
|--------------------------|-----------------------------------------------------------------------|
| `check`                  | Run all hk checks without requesting fixes.                           |
| `fix`                    | Apply deterministic hk fixes to the working tree.                     |
| `docs:check`             | Build the book, then validate documentation metadata and navigation.  |
| `docs:build`             | Build the mdBook site.                                                |
| `docs:deployment:enable` | Configure Pages and enable its repository gate through external `gh`. |
| `docs:serve`             | Serve mdBook on port 3000 by default or a supplied port.              |

The committed lock targets `linux-x64`, `linux-arm64`, `macos-x64`, and `macos-arm64`. Windows is not part of this
POSIX-shell task contract.

The mise environment routes hooks through mise with `HK_MISE=1` and sets `GIT_CONFIG_PARAMETERS="'merge.ff=only'"`, so
Git rejects merges that require a merge commit.

The universal tool count remains ten; `gh` is an external administrative prerequisite, not a mise tool. Pages requires
`build_type=workflow` plus `DOCS_DEPLOYMENT_ENABLED=true`. The build job has `contents: read`; only the deploy job has
`pages: write` and `id-token: write`.

Provisioning reports separate mise availability, lock, install, and hook states. Overall status is `succeeded`,
`degraded`, or `skipped`; failed or skipped stages include exact recovery commands.
