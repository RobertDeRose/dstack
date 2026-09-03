# Testing and tooling

## Local checks

```bash
uv run pytest
uv run pytest tests/acceptance
hk check -a
```

Fast tests isolate dStack adapters and validators. Acceptance tests execute Beads 1.2.2 and verify the native formula
graph, readiness, claims, gates, dependencies, worktrees, and Git evidence relied upon by the skills.

## hk and Beads

hk owns project formatting, linting, type checking, tests, and documentation validation. Its Git hooks call
`bd hooks run` for pre-commit, post-merge, and pre-push, allowing Beads to integrate through the existing hook manager
rather than a dStack hook protocol.

Beads setup and diagnostics remain native Beads concerns. dStack does not wrap `bd init`, `bd doctor`, hook installation,
synchronization, or database repair. Embedded workspaces should use the native commands supported by their selected
Beads release rather than treating `bd doctor` as a dStack prerequisite.
