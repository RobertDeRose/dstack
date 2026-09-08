# Feature lifecycle

This workflow is opt-in. It starts only when the user invokes `/plan-feature`, `/review-plan`, `/implement`,
`/close-feature`, `/audit-project`, or explicitly asks to use dStack. dStack setup and deterministic commands perform
their documented mechanics without creating or updating workflow issues.

## Native molecule

`dstack-feature` has five native steps:

```text
plan -> review -> approval -> implementation -> close
```

The implementation step is an epic containing dynamic tasks. Review creates each task with a direct blocker on the
approval step. The final `audit` step has one `children-of(implementation)` waits-for dependency; there is no fixed
close-review gate.

## Planning

`/plan-feature` runs `dstack init` and requires `dstack check formula` to validate committed policy before pouring new
work. It records the original request in the plan description, a publishable design fragment in the design field,
observable outcomes in acceptance criteria, and material questions and answers in native comments. The design contains
exactly six level-three headings: Goals, User-facing behavior, Implemented design, Compatibility and constraints,
Validation, and Non-goals. Nested subsections are allowed within those sections. Mechanical checks validate fields and
structure, not whether prose represents an unresolved decision. Planning focuses on user intent; it does not broadly
inspect the repository or create implementation tasks.

Planning closes only after its questions are resolved and `dstack check plan --bead <plan-bead>` succeeds.

## Review and approval

`/review-plan` first searches targeted project memories, then reconciles the design with relevant current code, tests,
and documentation. Current documentation and accepted decisions outrank stale memory; memory corrections require user
approval. It creates bounded implementation tasks with native dependencies. Each task stores planned scope in
`description`, the accepted approach and invariants in `design`, and observable outcomes in `acceptance_criteria`; it
does not use commit-type or scope labels. Before presenting the result, review validates fixed steps and task graph
invariants. Invocation never grants human approval.

## Implementation

`/implement` enters the registered worktree and resumes owned in-progress work before claiming a new native-ready task.
It reads the selected task's review comments and accepted fields. Only one agent writes a feature worktree at a time.
Task notes record current delivered outcomes as ordered one-line `Implementation:` fragments of at most 96 characters.
Technical punctuation is preserved; there is no English verb whitelist. Review rationale stays in comments and durable
rationale in linked decision Beads rather than duplicate commit prose.

Run the repository's documented validation before committing. Each repository-changing task owns one canonical commit
with a `Task:` trailer. A conventional native title prefix selects the type; otherwise it defaults to `feat`. Reopened
corrections revise obsolete notes and amend only the owning unpublished commit, replaying descendants without absorbing
unrelated fixups. Clean retries are no-ops. `dstack check task --bead <task>` verifies selected evidence, graph membership,
and cleanliness without hydrating every sibling. Close the task only after all checks pass. Implementation updates
current documentation but leaves the feature publication under `docs/src/features/<slug>/` to close review.

## Close

The public `/close-feature` operation reviews the feature before claiming the final step. Its internal ID and label
remain `audit` and `dstack:step:audit`. Close collects bounded facts with
`dstack audit --bead <root> --include-plan`, reads the plan and relevant accepted decisions, compares the delivered repository with approved intent, and returns clear defects to their owning task.
Unowned findings become one new implementation child; material ambiguity becomes a separate native gate that directly
blocks the close step without secondary parentage. When the answer changes approved intent, close records a decision,
updates the plan design and owning task acceptance criteria, and reopens that task for `/implement`. An unowned changed
outcome instead becomes a bounded correction task.

The close skill reviews before claiming the final step. When every current implementation child is closed, native
`children-of(implementation)` fan-in may expose the final step as ready; close deliberately leaves it unclaimed during
semantic review. A defect reopens its owning task for `/implement`, which blocks the still-open final step again through
the same native fan-in. Once review is clean and every implementation task is closed, close claims or resumes the final
step.

Only after review passes does close export the design, write the minimal feature documentation, and run feature-document
validation separately from the repository's own project validation. `dstack docs commit --bead <feature-root>` creates
the one allowed close-owned `docs(<slug>): <feature title>` commit with no body and a `Task:` trailer for the final
step. Rerunning it with one unpublished close commit and a clean worktree rewords stale canonical metadata without
creating duplicate evidence. Valid publication inherited unchanged from the base needs no new or empty close commit.

Close operates in the registered feature worktree. Documentation scaffolding is repeatable and does not replace prose;
the design export is checked against Beads at commit and final audit. After validation, explicitly close the
implementation epic, final step, and root, skipping already-closed items on resume. Verify their native statuses.
