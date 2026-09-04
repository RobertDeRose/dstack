# Feature lifecycle

This workflow is opt-in. It starts only when the user invokes `/plan-feature`, `/review-plan`, `/implement`, or
`/audit-feature`, or explicitly asks to use dStack. dStack setup and deterministic commands perform their documented
mechanics without creating or updating workflow issues.

## Native molecule

`dstack-feature` has five native steps:

```text
plan -> review -> approval -> implementation -> audit
```

The implementation step is an epic containing dynamic tasks. Review creates each task with a direct blocker on the
approval step. The audit has one `children-of(implementation)` waits-for dependency.

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
and documentation. It creates bounded implementation tasks with native dependencies. Each task stores planned scope in
`description`, the accepted approach and invariants in `design`, and observable outcomes in `acceptance_criteria`; it
does not use commit-type or scope labels. Before presenting the result, review validates fixed steps and task graph
invariants. Invocation never grants human approval.

## Implementation

`/implement` claims one native ready implementation task, prepares its verified feature worktree, and implements the
complete accepted outcome. During implementation, the agent appends concise, verb-led, one-line `Implementation:`
fragments to the task; each names one concrete change and is no more than 96 characters. dStack strips surrounding
whitespace and punctuation, adds `- ` without wrapping, and uses these notes—not planned description or design prose—as
the only source of commit bullets. Commit and task validation require native `in_progress` status and at least one
implementation note for repository changes. Each task owns one canonical `feat(<slug>)` commit with one `Task:` trailer.
Reopened corrections append notes and are fixup/autosquashed
into that commit when its history is unambiguous and unpublished; dStack refuses unsafe rewriting. The task owns its
code, tests, configuration, and current documentation. `dstack check task --bead <task>` validates the graph, evidence,
worktree, and `hk check -a` result before closure.

## Audit

`/audit-feature` collects bounded facts with `dstack audit`, compares the delivered repository with the approved intent,
and records clear findings or user questions in Beads.
