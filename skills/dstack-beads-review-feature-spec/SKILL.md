---
name: dstack-beads-review-feature-spec
description: "Materialize planned intent, reconcile it with the repository, and obtain authorization without coupling Beads to Git history."
---

# Review feature specification

Pass the selected planned-feature or current-molecule ID, slug, or title explicitly. Default the base branch to `dev`
when it exists, otherwise `main`, unless the user chose one. Omission is safe only inside the registered feature
worktree.

## Materialize the review boundary

Run the retained stateless mechanics:

```bash
"{baseDir}/../../bin/dstack" ctl feature initialize "<selector>" --base-branch "<base>"
"{baseDir}/../../bin/dstack" ctl feature claim-spec "<returned-root>"
"{baseDir}/../../bin/dstack" ctl feature scaffold-design "<returned-root>"
```

Initialization pours a planned feature or reuses an already initialized current molecule and conventional worktree. It
preserves planned intent, priority, and external blockers. Treat the returned root and worktree as authoritative.
Scaffolding creates the canonical design only when absent and never overwrites content. Complete every required section
with substantive content or `Not applicable — <specific reason>`; placeholders, duplicate/missing headings, and
unsupported local links fail before approval mutation.

## Reconcile intent with reality

In the returned worktree, read the complete Beads intent and canonical design, then inspect relevant architecture,
source, tests, durable documentation, dependencies, and other work. Materialize or refine
`docs/src/features/<slug>/design.md` so it covers:

- outcome, rationale, requirements, decisions, alternatives, and non-goals;
- existing patterns and why any new abstraction is necessary;
- interfaces, data flow, happy path, and observable success behavior;
- invalid input, persistence/state behavior, failure recovery, security, compatibility, and migration boundaries;
- behavior-first validation and regression expectations; and
- Documentation impact for all three audiences; use local Markdown links for every concrete affected surface and explain
  each `N/A`.

Resolve clear holes and collisions directly. Ask only for genuine product or architecture decisions.

## Reconcile the implementation graph

Inspect the current graph before mutation:

```bash
"{baseDir}/../../bin/dstack" ctl feature inspect "<returned-root>"
```

Reconcile the whole native graph: reuse/update valid tasks with native `bd update`; create missing outcomes;
close/supersede obsolete tasks with a reason; add real blockers with native `bd dep add`; remove obsolete blockers with
native `bd dep remove`; and preserve context as nonblocking relations. Do not duplicate tasks or maintain a shadow
graph. Create missing bounded outcomes through:

```bash
"{baseDir}/../../bin/dstack" ctl feature add-task "<returned-root>" --title "<title>" \
  --description-file "<temporary-description>" \
  --acceptance-file "<temporary-acceptance>" [--depends-on "<task-id>"]
```

Every task automatically depends on implementation approval. Add only real predecessors. Use observable outcomes, not
file lists or implementation names. Do not create reviewer, coordinator, status, documentation, reconciliation, or
speculative tasks; the closeout step is the sole final reconciliation. When repository
contents changed, commit the actual design/docs change with the specification Bead footer:

```bash
"{baseDir}/../../bin/dstack" ctl git commit --bead "<spec-id>" --subject "<subject>"
```

Review the complete final design, task graph, dependencies, and candidate diff. Present material decisions, findings,
validation expectations, and deferred risk, then ask for explicit human authorization. The command invocation itself is
not authorization. Do not approve while a consequential decision or finding is unresolved. After authorization, record
only the accepted content digest and native gate transition:

```bash
"{baseDir}/../../bin/dstack" ctl feature approve-spec "<returned-root>"
```

This stores no Git SHA. Return the authorized outcomes and `/implement-feature <returned-root>` as the next stage.
