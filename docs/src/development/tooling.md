# Testing and tooling

Run the fast suite and native acceptance suite with:

```bash
uv run pytest                 # xdist workers are enabled automatically
uv run pytest tests/acceptance
```

The default pytest configuration uses `pytest-xdist` with `-n auto`. Pass `-n 0` when a serial run is needed.

Run the complete repository contract with:

```bash
hk check -a
```

Fast tests cover stateless adapters and validators. Acceptance tests execute Beads 1.2.2 and verify the native formula,
readiness, claims, gates, dependencies, worktrees, and Git evidence used by the skills.

hk owns formatting, linting, type checking, tests, and documentation validation. Its Beads hooks integrate through the
native `bd hooks` commands.
