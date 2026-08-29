---
name: dstack-beads-plan-feature
description: "Discover and preserve sufficiently lossless planned feature intent in Beads without materializing repository workflow."
---

# Plan feature

Before native Beads planning, run `"{baseDir}/../../bin/dstack" ctl infra check`. This initializes Beads when needed and confirms the packaged formula contracts used for new work; no historical workflow migration occurs.

Decide what should be built and why. Planning owns product discovery and writes only durable Beads intent; repository
specification and authorization belong to `/review-feature-spec`.

## Resolve context

Treat input as an exact ID, slug, title, or new request. Inspect existing Beads features and only the architecture,
product docs, source, tests, and related work needed to understand the outcome. Resolve an existing candidate with:

```bash
"{baseDir}/../../bin/dstack" ctl feature resolve "<selector>"
```

Update only one open planned feature labeled `dstack:feature-idea` and `feature:<slug>`. Replanning reuses that Beads ID
and keeps its established `feature:<slug>` identity stable; a changed title does not rename the slug. If identity is
ambiguous or closed, ask the user. If it is a current molecule, stop and return `/review-feature-spec`; planning must
not change materialized or authorized scope.

## Discover intent

Do not merely summarize the request. Identify consequential ambiguity and ask focused questions. Explore alternatives
and tradeoffs only when they materially affect behavior, compatibility, risk, cost, or maintenance. Reuse existing
patterns and reject speculative abstraction.

Before persistence, establish or explicitly defer:

- the outcome and why it matters;
- requirements and relevant repository context;
- decisions and rationale;
- alternatives and material tradeoffs;
- non-goals;
- observable success;
- failure and compatibility expectations;
- documentation expectations for users/operators, developers/reviewers, and future agents/auditors; and
- deferred questions and real dependencies.

## Persist planned intent

Write a temporary Markdown body outside the repository. Give each topic its own heading: Goal; Why; Requirements;
Relevant repository context; Decisions and rationale; Alternatives and tradeoffs; Non-goals; Observable acceptance;
Failure and compatibility expectations; Documentation expectations; Deferred questions; and Dependencies.

Persist multiline intent as data through `--body-file`, never as shell syntax. Derive priority from planning evidence;
ask only when the choice is consequential and genuinely ambiguous. Create one new idea with native Beads:

```bash
bd create --type epic --title "<title>" \
  --labels "dstack:feature-idea,feature:<slug>" \
  --body-file "<temporary-body>" --acceptance "<observable-acceptance>" \
  --priority "<0-4>"
```

Or update every changed durable field on the resolved open planned feature:

```bash
bd update "<id>" --title "<title>" --body-file "<temporary-body>" \
  --acceptance "<observable-acceptance>" --priority "<0-4>"
```

Before changing blockers, read the native issue and its dependency records:

```bash
bd show "<id>" --json
```

Reconcile only the planning blocker relationships in scope. Keep a still-needed edge, add a newly required blocker with
`bd dep add "<id>" "<blocker-id>"`, and remove a previous planning blocker that the final plan rejects with
`bd dep remove "<id>" "<blocker-id>"`. Preserve other dependency types and any blocker outside the replanning decision.
Never maintain a shadow dependency list or replace Beads' graph from body text.

Read the issue back with `bd show "<id>" --json`; verify its title, complete body, acceptance, priority, stable slug
label, and blocker graph. Remove the temporary file after verification. Do not create lifecycle or implementation
children.

Do not initialize a workflow, create a branch/worktree, write repository design or planning files, stage or commit Git
content, or change readiness outside native Beads operations.

Return the planned Bead, durable decisions and rationale, deferred questions, real dependencies, and
`/review-feature-spec <id>` as the next stage.
