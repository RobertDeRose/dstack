# Testing and tooling

## Local checks

```bash
uv run pytest
uv run pytest tests/acceptance
hk check -a
```

Fast tests isolate dStack adapters and validators. Acceptance tests execute the supported Beads binary and verify the
native formula graph, readiness, claims, gates, dependencies, worktrees, and Git evidence relied upon by the skills.

## hk and Beads

hk owns project formatting, linting, type checking, tests, and documentation validation. Its Git hooks call
`bd hooks run` for pre-commit, post-merge, and pre-push, allowing Beads to synchronize through the existing hook manager
rather than installing a competing hook protocol.

`bd doctor` is the authoritative integration diagnostic. dStack reports its result but does not duplicate the diagnostic
model.
