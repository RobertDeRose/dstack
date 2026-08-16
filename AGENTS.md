# dstack repository guidance

Keep dstack a thin policy layer over Beads and Git.

## Authorities

- Beads owns formulas, protos, molecules, work, dependencies, gates, readiness,
  claims, TODOs, comments, relationships, worktree records, and completion.
- Git owns source, branches, commits, diffs, and delivery boundaries.
- dstack owns skills, prompt aliases, review policy, and the deterministic
  formula installer.

## Hard constraints

- Do not add a dstack task store, workflow-state store, scheduler, ready-work
  computation, dependency planner, fan-in implementation, approval engine, CI
  poller, PR poller, ownership ledger, or reviewer lifecycle graph.
- Do not restore `tasks.md`; implementation and audit work belongs in Beads.
- Do not replace Beads formulas, molecules, gates, TODOs, claims, worktrees, or
  graph relationships with wrappers.
- Do not encode reviewer seats, pass numbers, replacement counters, or
  coordinator ceremony in formulas.
- Do not impose a terminal review limit. Explicit user authorization always
  permits another review.
- Do not classify a later correctness or test finding as redesign unless the
  accepted design itself must change.
- Do not make optional metadata a prerequisite for serial execution.
- Normal workflows never migrate or rewrite historical workflow topology.
- One implementation or corrective Bead is one intended Git commit boundary by
  default.
- Helpers may install or validate configuration, but workflow execution must use
  native `bd` commands directly.

## Formula design

Formulas encode only stable lifecycle skeletons. Dynamic implementation and
audit tasks are created under the poured workstream epics and participate in
native dependency, gate, and fan-in behavior.

## Phase 1

Only the original feature lifecycle and the original three-tier project
alignment lifecycle are in scope. Expert meetings, code intelligence, inline
review UI, review wisps, and parallel writers are later phases.
