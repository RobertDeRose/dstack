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
- workflow migration engines.

The single compatibility exception is `/adopt-feature`, which translates one
active legacy dstack feature into the current native formula skeleton using
ordinary Beads operations. It does not maintain migration state.

## Stable workflow skeletons

The two formulas encode only stable steps:

```text
dstack-feature:
  specification -> gated approval task
  implementation epic -> dynamic children depend on approval
  closeout needs approval and waits for implementation children

dstack-project-alignment:
  analysis -> gated approval task
  corrections epic -> dynamic children depend on approval
  landing needs approval and waits for correction children
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

## Separation of concerns

Beads owns work identity, dependencies, readiness, decisions, validation state,
and durable review findings. Git owns source/docs and commit history. Repository
docs explain the product and design; they are not workflow state.

Do not duplicate Git history into Beads. Never store implementation/specification
commit SHAs in Beads fields, metadata, comments, or external references. Every
dstack-created commit instead carries a stable footer:

```text
Beads: <work-item-id>
```

That footer is the only Git↔Beads implementation linkage. If Git history is
rewritten, the footer moves with the rewritten commit and no Beads repair is
required. One dynamic implementation or correction Bead is one intended Git
commit by default. Specification and closeout/landing work may each produce one
bounded commit when repository content actually changes. Never create a commit
whose only purpose is workflow bookkeeping.

Use `scripts/git_evidence.py` for deterministic evidence lookup and design-drift
checks instead of making the agent reason about commit ancestry or copy SHAs into
Beads.

## Beads runtime state and Git

The Beads Dolt database owns durable workflow state. Do not stage, commit, or
restore `.beads/interactions.jsonl` as part of feature work. It is runtime/export
state, not a feature commit boundary.

If `.beads/interactions.jsonl` is tracked by Git, treat that as legacy repository
configuration. Preserve the file contents and use `/setup-project --force` for
the one-time untracking migration. Never recommend `git restore` on a freshly
written interaction log merely to make the worktree clean.
