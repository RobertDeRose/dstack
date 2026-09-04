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
Validation, and Non-goals. Planning focuses on user intent; it does not broadly inspect the repository or create
implementation tasks.

Planning closes only after its questions are resolved and `dstack check plan --bead <plan-bead>` succeeds.

## Review and approval

`/review-plan` first searches targeted project memories, then reconciles the design with relevant current code, tests,
and documentation. Current documentation and accepted decisions outrank stale memory; memory corrections require user
approval. It creates bounded implementation tasks with native dependencies. Each task stores planned scope in
`description`, the accepted approach and invariants in `design`, and observable outcomes in `acceptance_criteria`; it
does not use commit-type or scope labels. Before presenting the result, review validates fixed steps and task graph
invariants. Invocation never grants human approval.

## Implementation

`/implement` claims one native ready implementation task, prepares its verified feature worktree, and implements the
complete accepted outcome. During implementation, the agent appends concise, verb-led, one-line `Implementation:`
fragments to the task; each names one concrete change and is no more than 96 characters. dStack strips surrounding
whitespace and punctuation, then adds a dash-and-space prefix without wrapping, and uses these notes—not planned
description or design prose—as the only source of commit bullets. Commit and task validation require native
`in_progress` status and at least one implementation note for repository changes. Each task owns one canonical
`feat(<slug>)` commit with one `Task:` trailer. Reopened corrections append notes and are fixup/autosquashed into that
commit when its history is unambiguous and unpublished; dStack refuses unsafe rewriting. The task owns its code, tests,
configuration, and current documentation. `dstack check task --bead <task>` validates the graph, evidence, and clean
worktree. The skill separately runs the target repository's documented validation contract, then closes the task so
native task dependencies can expose downstream work. Implementation does not write the feature publication under
`docs/src/features/<slug>/`; close owns it after semantic review.

## Close

The public `/close-feature` operation reviews the feature while a formula-generated human gate keeps the final step
blocked. Its internal ID and label remain `audit` and `dstack:step:audit`. Close collects bounded facts with
`dstack audit`, compares the delivered repository with approved intent, and returns clear defects to their owning task.
Unowned findings become one new implementation child; material ambiguity becomes a separate native gate that directly
blocks the close step without secondary parentage. When the answer changes approved intent, close records a decision,
updates the plan design and owning task acceptance criteria, and reopens that task for `/implement`. An unowned changed
outcome instead becomes a bounded correction task.

The close-review gate remains unresolved even if native `children-of(implementation)` fan-in has already observed prior
children as complete. A defect reopens its owning task for `/implement`. Once the complete review is clean and every
implementation task is closed, close resolves the fixed gate and claims the final step.

Only after review passes does close export the design, write the minimal feature documentation, and run feature-document
validation separately from the repository's own project validation. `dstack docs commit --feature <feature-root>`
creates the one allowed close-owned `docs(<slug>): <feature title>` commit with no body and a `Task:` trailer for the
final step. Rerunning it with one unpublished close commit and a clean worktree rewords stale canonical metadata without
creating duplicate evidence.
