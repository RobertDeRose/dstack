# 0001: Authority ownership

- **Status:** Accepted
- **Supersedes:** None
- **Superseded by:** None

## Context

Workflow correctness failed when orchestration duplicated readiness, dependencies, claims, or delivery history outside
their native authorities.

## Decision

Beads owns work, dependencies, gates, readiness, claims, and completion. Git owns repository content, worktrees,
commits, refs, and delivery history. Documentation owns stable product and architecture intent. dStack controllers are
stateless deterministic adapters that query those authorities each time.

## Consequences

dStack does not add a database, task manifest, scheduler, ownership ledger, review topology, or Git-history mirror.
Narrow safety vetoes may compensate for a pinned native limitation, but they cannot calculate positive readiness.
