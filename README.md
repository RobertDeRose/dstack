<!-- rumdl-disable-file MD041 -->

<p align="center">
  <img src="docs/src/assets/img/dstack_logo.png" alt="dStack logo">
</p>

`dStack` gives software-engineering agents a small, deterministic set of repository operations around a Beads-backed
feature workflow.

- **Beads** owns plans, decisions, tasks, dependencies, claims, readiness, and completion.
- **Git** owns repository content, branches, worktrees, and history.
- **Workflow commands** (`/plan-feature`, `/review-plan`, `/implement`, `/close-feature`, `/audit-project`) guide
  semantic
  work.
- **dStack CLI commands** validate policy and perform deterministic repository mechanics.

The workflow is opt-in. Ordinary requests do not create Beads issues or activate dStack tracking.

## Install

Runtime requirements are Git, Python 3.14, and Beads 1.2.2.

```bash
uv tool install --python 3.14 /path/to/dstack
dstack install
```

Then initialize each repository that will use dStack:

```bash
cd /path/to/repository
dstack init
```

Review and commit the installed dStack formula, then verify it:

```bash
dstack check formula
```

See [Getting started](docs/src/getting-started/index.md) for the complete first-run workflow.

## Workflow

A feature moves through four user-facing stages with an explicit approval between review and implementation:

```text
/plan-feature <request>
        |
        v
/review-plan <feature>
        |
        v
review and approve the proposed scope
        |
        v
/implement <feature>
        |
        v
/close-feature <feature>
```

`/audit-project` is separate from the feature lifecycle. It reviews current project drift and creates a normal
remediation
plan only when work is needed.

## Documentation

The mdBook under [`docs/`](docs/src/index.md) is the canonical documentation:

- [Getting started](docs/src/getting-started/index.md)
- [Operations](docs/src/operations/index.md)
- [Architecture](docs/src/architecture/index.md)
- [CLI reference](docs/src/reference/cli.md)
- [Recovery](docs/src/operations/recovery.md)

## Development

This repository uses `uv`, hk, and mdBook for its own validation:

```bash
uv run pytest
uv run pytest tests/acceptance
hk check -a
```

Use `-n 0` for a serial pytest run. Acceptance tests require Beads 1.2.2 on `PATH`.
