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

`/plan-feature` records the request, repository evidence, questions and answers, decisions, rationale, acceptance
criteria, non-goals, and documentation impact in the plan Bead. It does not create implementation tasks.

Planning closes only after the ambiguity pass is complete and `dstack check plan --bead <plan-bead>` succeeds.

## Review and approval

`/review-plan` compares the plan with current repository behavior and creates bounded implementation tasks with native
dependencies. It presents the reviewed graph for explicit human approval before implementation becomes ready.

## Implementation

`/implement` claims one native ready implementation task, prepares its verified feature worktree, and implements the
complete accepted outcome. The task owns its code, tests, configuration, and current documentation.
`dstack check task --bead <task>` validates the graph, evidence, worktree, and `hk check -a` result.

## Audit

`/audit-feature` collects bounded facts with `dstack audit`, compares the delivered repository with the approved intent,
and records clear findings or user questions in Beads.
