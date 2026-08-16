---
name: dstack-beads-core
description: "Shared Beads-native workflow, review, discovery, Git, and authority rules for every dstack command."
---

# dstack core

dstack is workflow policy, not a workflow engine.

## Read first

Before running a dstack lifecycle command, read the relevant references in this
skill:

- `references/beads-workflows.md`
- `references/review-loop.md`
- `references/discoveries.md`
- `references/worktrees-and-delivery.md`

## Preflight

From the target repository, run:

```bash
python3 "{baseDir}/scripts/setup.py" doctor --root .
```

If setup is missing, route to `/setup-project`. Do not silently install,
initialize, migrate, repair, or publish Beads from another workflow command.

## Native Beads rule

Use formulas, molecules, dependencies, gates, ready work, atomic claims, TODOs,
comments, graph relationships, and native worktrees directly through `bd`.

Do not add a helper for:

- workflow resolution beyond reading Beads JSON;
- status or progress;
- readiness or claiming;
- dependency or fan-in computation;
- approval state;
- CI or PR polling;
- task ownership;
- worktree lifecycle;
- workflow migration.

## Stable workflow skeletons

The two formulas encode only stable steps:

```text
dstack-feature:
  specification -> human gate -> implementation epic -> closeout

dstack-project-alignment:
  analysis -> human gate -> corrections epic -> landing
```

Real implementation and correction tasks are dynamic children of the relevant
workstream epic. Reviewer seats and review iterations are never Beads lifecycle
children.

## User authority

Only concrete repository integrity, destructive-risk, external-policy, or
ambiguous-target conditions are hard stops. Missing optional metadata degrades
capability rather than blocking serial work.

A reviewer may recommend against proceeding but cannot prevent a user-authorized
additional review. Do not claim approval when unresolved risk remains; record
`accepted risk` when the user explicitly accepts it and repository policy allows
that result.

## Commit boundaries

One dynamic implementation or correction Bead is one intended Git commit by
default. Specification and closeout/landing work may each produce their own
bounded commits. Beads comments record durable evidence; do not create
bookkeeping-only Git commits.
