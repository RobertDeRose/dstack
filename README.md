<!-- rumdl-disable-file MD041 -->

<p align="center">
  <img src="docs/src/assets/img/dstack_logo.png" alt="dStack logo">
</p>

`dStack` helps software-engineering agents plan, review, implement, and close feature work. It pairs Pi workflow
commands
such as `/plan-feature` and `/implement` with a small CLI for deterministic repository operations around Beads and Git.

## Install

Runtime requirements are Git, Python 3.14, Beads 1.2.2, and `uv`.

```bash
uv tool install git+https://github.com/RobertDeRose/dstack
dstack install
```

Initialize each repository that will use dStack:

```bash
cd /path/to/repository
dstack init
```

Review and commit the generated `.beads/` policy changes, then verify the committed formula:

```bash
dstack check formula
```

Continue with [Getting Started](docs/src/getting-started/index.md) for the feature workflow and project auditing.

## Documentation

- [Getting Started](docs/src/getting-started/index.md)
- [Interrupted Skill Recovery](docs/src/recovery.md)
- [Architecture](docs/src/architecture/index.md)
- [Development and Contributions](docs/src/development/index.md)
- [References](docs/src/reference/index.md)

## Development

This repository uses `uv`, hk, and mdBook for its own validation:

```bash
uv run pytest
uv run pytest tests/acceptance
hk check -a
```

Use `-n 0` for a serial pytest run. Acceptance tests require Beads 1.2.2 on `PATH`.
