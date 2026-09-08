---
dstack-managed: true
name: dstack-review-plan
description: "Reconcile a completed feature plan with memory and repository facts, then create its native task graph."
disable-model-invocation: true
---

# Review plan

## dStack operations

Use these dStack commands after reconciling the reviewed plan and task graph:

```bash
dstack check plan --bead <plan>
dstack check review --bead <root>
```

Both must pass before closing the review step. The review check validates the fixed workflow steps, implementation task
shape, approval blockers, persistent close blockers, and that implementation work is not ready before approval.

## Review

Resolve the feature with `bd mol current <root> --json`. Read the plan and review step with
`bd show <plan> <review> --include-comments --json`. If review is already closed, do not recreate tasks or rerun the
preapproval check; continue to Approval. Otherwise continue an in-progress review or claim only a native-ready open
review.

Search `bd memories <focused terms> --json`, then recall only relevant keys. Inspect only relevant source, tests,
documentation, and decisions. When useful, review independently from implementation, documentation, and risk
perspectives, then keep only synthesized findings. Correct clear plan defects; ask the user when authority remains
materially ambiguous.

Record durable decisions as native decision Beads labeled `decision:<slug>` and link each to the feature root with one
exact `relates-to` dependency.

## Create implementation work

Inspect existing implementation children first and reconcile partial review work by ID instead of creating duplicates.
Create bounded task-shaped outcomes directly under the implementation epic. Use one native `bd create` invocation with
`--parent`, `--no-inherit-labels`, `--labels`, `--description`, `--design`, `--acceptance`, and
`--deps blocked-by:<approval>` so a new task never temporarily lacks its approval blocker. Immediately make the final
step depend on the new task with `bd dep add <audit> <task> --type blocks`. Preserve that edge after the task closes so
a later reopen blocks close again. On resume, repair a missing edge on an existing child before continuing rather than
creating a replacement task.

Each task needs:

- `dstack:work:implementation` and no inherited structural label;
- planned scope and non-goals in `description`, not commit prose;
- accepted approach, invariants, and boundaries in `design`;
- observable outcomes in `acceptance_criteria`; and
- real native dependencies, including the direct approval blocker.

Leave execution notes empty. During implementation, delivered repository work is recorded as ordered
`Implementation: <completed increment>` notes; `No repository change: <specific reason>` is reserved for an intentional
no-change task. Do not create commit-type or scope labels. A conventional prefix in the task title may select a
non-`feat` commit type when appropriate.

Add ordering dependencies only where execution order is real. Every implementation task must remain a direct native
blocker of the final step; `dstack check review --bead <root>` rejects a task that lacks that completion edge.

No implementation task may be ready before approval. Let Beads validate dependency legality and readiness, including
cross-feature blockers and native conditional dependencies; unrelated project cycles do not invalidate this feature. Run
the two dStack checks above, then close the review step and present scope, risks, decisions, and the task graph. Review
never grants approval.

## Approval

Read the approval step with comments. If it is already closed, preserve its recorded approval and return
`/implement <root>`. Otherwise require explicit user approval for the reviewed intent; neither invocation nor a closed
review grants it. Resolve only the formula gate with await ID `approve-<slug>-plan`, continue an in-progress approval or
claim it only when open and ready, record the approval evidence, close it, and return `/implement <root>`.
