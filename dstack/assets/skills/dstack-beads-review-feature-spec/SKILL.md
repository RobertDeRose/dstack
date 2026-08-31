---
dstack-managed: true
name: dstack-beads-review-feature-spec
description: "Review new feature intent or audit existing approved work against the current formula contract."
---

# Review feature specification

Pass the selected feature ID, slug, or title explicitly. Default the base branch to `dev` when it exists, otherwise
`main`, unless the user chose one. Omission is safe only inside the registered feature worktree.

## Formula compatibility audit

When explicitly reviewing an already approved feature, run `dstack ctl feature inspect "<feature>" --verbose` and
compare its recorded formula-contract version with the current packaged contract. A stale or missing version does not
gate native-ready implementation work and does not create a Bead, alter dependencies, reopen steps, or normalize the
molecule. Review the existing approved Beads intent in place using only the accepted design/task facts needed by the
semantic comparison.

1. Compare semantic coverage with the current requirements in this skill. Different task names/grouping are not findings
   when the existing plan covers the same outcomes.
2. If there is no material gap, run `dstack ctl feature audit-complete "<feature>"`. This explicit operation updates
   only the feature root's formula-contract version. No user approval is required.
3. If changes are required, present only the minimal design/task/dependency delta and why each change is required. Stop
   for explicit user approval **before** any mutation. After approval, run `feature reauthorize` and reuse the normal
   specification/human-gate/approval mechanics below, changing only the approved delta.

## Normal review and approved audit changes

Materialize or reuse the review boundary. If the feature is already initialized, reuse its current molecule/worktree
rather than creating another:

```bash
dstack ctl feature initialize "<selector>" --base-branch "<base>"
dstack ctl feature claim-spec "<returned-root>"
dstack ctl feature scaffold-design "<returned-root>"
```

For an already-approved feature whose compatibility audit found changes, first run `feature reauthorize`
**only after user approval**. Scaffolding creates missing canonical documentation without overwriting project content.

Read complete Beads intent and the canonical design, then inspect only relevant architecture, source, tests, durable
documentation, dependencies, and other work. Reconcile `docs/src/features/<slug>/design.md` using only the six canonical
sections: Outcome, Non-goals, Design, Failure/security/compatibility, Validation, and Documentation impact. Capture
rationale, requirements, existing patterns, interfaces/data flow, observable behavior, risks, and alternatives inside
those sections only when material; do not create extra mandatory sections. Documentation impact should link the durable
surfaces actually affected.

Inspect the current graph with:

```bash
dstack ctl feature inspect "<returned-root>" --verbose
```

Reuse/update valid tasks with native `bd update`; create only missing outcomes; close/supersede obsolete tasks with a
reason; add/remove only real blockers with native `bd dep add` / native `bd dep remove`. Do not create reviewer,
coordinator, status, documentation, reconciliation, or speculative tasks. Create missing bounded outcomes through
`feature add-task`; every task automatically depends on implementation approval.

When repository content changed, commit the real design/docs change with the specification Bead footer. Review the final
design, task delta/graph, dependencies, and candidate diff. For a normal review, ask for explicit human authorization;
invocation itself is not authorization. For a compatibility audit, the earlier approval covers only the presented delta;
do not expand it silently.

After authorization, run:

```bash
dstack ctl feature approve-spec "<returned-root>"
```

Approval records the accepted design digest and current formula contract version; it stores no Git SHA. Return the
authorized outcomes and `/implement-feature <returned-root>` as the next stage.
