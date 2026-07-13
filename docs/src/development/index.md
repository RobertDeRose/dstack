# Developing dstack

## Repository areas

- `skills/`: canonical skill definitions, scripts, references, and the bundled setup template.
- `tests/`: repository, migration, setup, update, and workflow validation.
- `copier.yml`: repository-development Copier entry point.
- `mise.toml`: reproducible tool and task interface.
- `hk.pkl`: shared local and CI quality policy.
- `docs/`: this mdBook and feature planning records.

## Setup

Install declared tools with `mise install`. The post-install hook installs hk through mise so Git hooks use the same
tool versions as manual checks.

## Validation

```bash
mise run check
mise run docs:build
uv run --frozen --group test pytest -m "not integration and not external"
uv run --frozen --group test pytest -m integration
uv run --frozen --group test pytest -m external
```

Use `mise run fix` for deterministic formatting fixes. The full serial test suite is
`uv run --frozen --group test pytest`.

## Change discipline

Keep both Copier entry points aligned. Template changes require generated-project tests and must preserve Copier update
compatibility. Skill versions are synchronized during semantic release. Changes to workflow behavior must update the
owning skill, tests, reader documentation, and feature evidence in the same work unit.

See [Feature lifecycle](feature-lifecycle.md) for the repository's planning and delivery workflow.
