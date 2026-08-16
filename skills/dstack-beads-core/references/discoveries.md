# Discovered work

Do not let incidental findings expand or block the current task by default.

## Fix now

Fix a finding in the current task when it is clearly required by the task's
accepted outcome and remains within its safe commit boundary.

## Quick TODO

Use a Beads TODO for a small informal follow-up that should not interrupt current
work:

```bash
bd todo add "<short follow-up>"
bd dep add <todo-id> <current-task-id> --type discovered-from
```

Add a concise description or labels with `bd update` when useful. TODOs are
ordinary Beads work and may later be promoted into a richer task or bug.

## Durable task or bug

Create a fully specified Bead when the finding is significant, risky, requires
separate acceptance criteria, or belongs to another feature. Link it with
`discovered-from`. Add a blocking dependency only when the current task truly
cannot be correct without the new work.

## Context-only relationship

Use a nonblocking `related` relationship for useful context that does not imply
execution order or provenance.

## Prohibited behavior

- Do not turn every reviewer observation into a new task.
- Do not silently broaden the selected task.
- Do not make unrelated discovered work block task closure.
- Do not create a dstack-specific discovery ledger.
