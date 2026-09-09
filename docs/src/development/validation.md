# Testing and validation

Run the repository checks before opening or updating a pull request.

## Tests

Run the complete pytest suite with:

```bash
uv run pytest
```

The default pytest configuration enables `pytest-xdist` automatically. Use `-n 0` when a serial run is useful.

For a narrower run:

```bash
uv run pytest tests/fast
uv run pytest tests/acceptance
```

The acceptance suite requires Beads 1.2.2 on `PATH`; `mise install` installs the repository's configured Beads version.

## Linters, formatters, types, and documentation

Run the repository-wide hk contract with:

```bash
hk check -a
```

This checks the file types configured in `hk.pkl`, including Python linting and formatting, type checking, Markdown,
structured configuration, GitHub Actions, and a clean mdBook build.

Documentation can also be built directly through the repository task:

```bash
mise run docs:build
```

## Release integrity

Changes that affect packaging, installation, generated assets, or release behavior should also run:

```bash
mise run release-check
```

The release check builds and verifies the project from a clean clone rather than relying on the current working tree.

## Pull-request checks

GitHub Actions runs the same categories independently for pull requests: hk validation, fast behavior tests, real-Beads
acceptance tests, and release integrity. A local change should be considered ready for review only after the relevant
checks above pass.
