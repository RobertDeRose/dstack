# Repository tooling

The repository keeps development commands in a small number of tools so local work and CI use the same entry points.

## Python and uv

The `dstack` CLI is implemented in Python 3.14. `pyproject.toml` defines the package, runtime dependency, development
dependencies, pytest configuration, and Ruff settings. `uv.lock` records the resolved Python dependency set.

Use `uv` to synchronize the development environment and run Python commands without maintaining a separate virtualenv
workflow:

```bash
uv sync --dev --locked
uv run pytest
```

## mise

[mise](https://mise.jdx.dev/) owns the repository's development tool versions and repeatable tasks. `mise.toml` pins or
selects the tools used by development and CI, including Python, Beads, hk, mdBook, Ruff, rumdl, ty, and supporting
linters.

The repository currently defines these tasks:

```text
docs:build      Build the mdBook site
docs:serve      Serve the documentation locally
release-check   Build and verify release artifacts from a clean clone
```

Run a task with `mise run <task>`, for example:

```bash
mise run docs:serve
mise run release-check
```

## hk

[hk](https://hk.jdx.dev/) owns repository checks and Git-hook orchestration through `hk.pkl`. It runs the configured
formatting, linting, type checking, structured-configuration, GitHub Actions, and mdBook checks.

The hook configuration also delegates Beads hook behavior at the appropriate Git lifecycle points:

- `pre-commit` runs the configured checks with fixes enabled and then the Beads pre-commit hook.
- `pre-push` runs the Beads pre-push hook.
- `post-merge` runs the Beads post-merge hook.

Run the complete hk check directly with:

```bash
hk check -a
```

Tests remain a separate validation step and are run with pytest; see [Testing and validation](validation.md).
