---
dstack-managed: true
name: dstack-beads-plan-feature
description: "Discover and preserve sufficiently lossless planned feature intent in Beads without materializing repository workflow."
---

# Plan feature

Before native Beads planning, run `dstack ctl infra check`. This initializes Beads when needed and confirms the packaged
formula contracts used for new work; no historical workflow migration occurs.

Decide what should be built and why. Planning owns product discovery and writes only durable Beads intent; repository
specification and authorization belong to `/review-feature-spec`.

## Resolve context

Treat input as an exact ID, slug, title, or new request. Inspect existing Beads features and only the architecture,
product docs, source, tests, and related work needed to understand the outcome. Resolve an existing candidate with:

```bash
dstack ctl feature resolve "<selector>"
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

Create or update the planned feature through the controller, which owns native Beads writes and blocker reconciliation:

```bash
dstack ctl feature plan "<existing-selector-if-any>" \
  --title "<title>" --slug "<slug-for-new-work>" \
  --body-file "<temporary-body>" --acceptance "<observable-acceptance>" \
  --priority "<0-4>" --depends-on "<blocker-id>"
```

Omit the selector when creating new work and repeat `--depends-on` as needed. Replanning keeps the established slug,
updates only the requested durable fields, and reconciles only blocking dependencies on the planned root. Remove the
temporary file after the controller confirms convergence. Do not create lifecycle or implementation children.

Do not initialize a workflow, create a branch/worktree, write repository design or planning files, stage or commit Git
content, or change readiness outside native Beads operations.

Return the planned Bead, durable decisions and rationale, deferred questions, real dependencies, and
`/review-feature-spec <id>` as the next stage.
