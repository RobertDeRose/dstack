# dStack Beads context

This project uses Beads only for an explicitly activated dStack workflow.

## Activation

Do not infer activation from `.beads`, installed skills, this file, or `bd` availability. For ordinary requests, do not
run `bd`, create issues, or require initialization.

Only `/plan-feature`, `/review-plan`, `/implement`, `/close-feature`, `/audit-project`, or an explicit request to use
dStack activates workflow tracking. An explicitly requested dStack command performs only its documented deterministic
mechanics.

Do not install generic Beads agent instructions or hooks. Do not run `bd prime` automatically.

## Authority

Within an active workflow, Beads owns plans, decisions, tasks, dependencies, gates, claims, readiness, completion, and
durable project memory. Git owns repository content, branches, worktrees, and history. Current repository documentation
and accepted decisions outrank stale memory.

Use the feature-scoped native queue and dStack's deterministic checks. Never maintain a Markdown task list, readiness
cache, commit map, audit packet, or other shadow workflow state.

## Memory exception

`/review-plan` and `/audit-project` may search and recall only targeted Beads memories. `/close-feature` may propose a
reusable memory addition, correction, or retirement, but it must show the exact change and receive user approval before
writing. Memory is advisory context, not live status or completion evidence.

## Lifecycle

```text
plan -> review -> human approval -> implementation tasks -> close
```

Planning captures intent in native description, design, and acceptance fields. Review reconciles memory and repository
facts and creates native work. Implementation resumes owned in-progress work before claiming a new ready task, reads selected task review comments,
and keeps `Implementation:` notes as the current delivered outcome. It validates before using those notes for one
canonical `Task:` commit and closing the task. One writer owns each feature worktree. The final internal `audit` step remains open while `/close-feature` reviews and returns defects. Native
implementation fan-in blocks it whenever implementation work is open; close claims it only after review passes, then writes and
validates feature documentation against the native design. Close explicitly closes the implementation epic, final
step, and root; no second phase tracker or recovery journal exists.

`/audit-project` audits current project drift and, when remediation is needed, creates and completes only the plan step
of a normal feature before returning `/review-plan`.
