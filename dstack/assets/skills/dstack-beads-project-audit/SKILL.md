---
name: dstack-beads-project-audit
description: "Audit current code and documentation, then propose ordinary corrective feature work."
dstack-managed: true
---

# Project audit

Perform a read-only, repository-grounded audit. Do not create or mutate Beads,
files, branches, worktrees, or commits.

1. Establish the requested scope; default to the current repository.
2. Read the current architecture, development, operations, reference, security,
   and feature documentation that governs the scope. Inspect the relevant source,
   tests, package assets, and native Beads/Git state. Treat historical feature
   records as history, not current authority, unless current documentation adopts
   them.
3. Compare documented intent with observable code and tests. Report only
   evidence-backed contradictions, behavioral drift, or consequential ambiguity.
   For each finding, cite paths and line ranges, state the documented and observed
   behavior, and explain the user-visible or delivery risk.
4. Present a **proposed corrective feature epic** containing a concise outcome,
   non-goals, acceptance criteria, and bounded implementation subtasks. Each
   subtask must describe an externally meaningful result, its dependencies, and
   the smallest useful validation. Keep documentation work in the feature's
   final closeout rather than creating a parallel documentation workflow.
5. Stop at the proposal. If the user accepts it, pass the lossless epic intent to
   `/plan-feature`; after specification review and explicit approval, use the
   ordinary feature graph and `/implement-feature` for every implementation
   subtask. Do not create an audit root, correction ledger, packet, or shadow
   state merely to hold the proposal.

If no material finding is supported, say so and do not invent corrective work.
