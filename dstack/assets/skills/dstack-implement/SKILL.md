---
dstack-managed: true
name: dstack-implement
description: "Claim and implement native ready work with deterministic worktree, commit, evidence, and validation checks."
---

# Implement

Use this skill only when explicitly invoked; that invocation activates the dStack workflow. Within an active workflow,
Beads is the only next-work surface. Do not read a task list file or maintain a separate progress record.

## Establish the worktree

Run:

```bash
dstack worktree --bead <feature-root>
```

Change into the returned worktree and verify the active branch matches the returned `feat/<slug>` branch. Do not run
`bd prime`; this skill already supplies the active dStack workflow context.

## Claim one task

```bash
bd ready \
  --parent <implementation-epic> \
  --label dstack:work:implementation \
  --claim \
  --json
```

Resolve the implementation epic from the formula step label before claiming. Read the claimed task, its direct blockers,
referenced decisions, and only the source and documentation needed for that outcome. If no implementation task is ready,
report native blockers; do not invent a dStack phase or claim the audit.

## Implement the complete accepted outcome

Implement the smallest complete change satisfying the task. Keep code, tests, configuration, and current
user/developer/future-agent documentation aligned in the same unit of work. Do not postpone documentation to a closeout
phase.

When new product or architecture ambiguity appears, record it on the task and ask the user rather than guessing. Clear
incidental defects may be fixed in scope. Significant separate work becomes a native Beads task linked with
`discovered-from`.

Review the complete diff, stage only task-owned repository changes, and commit through dStack so the subject and footer
come from the Bead:

```bash
dstack commit --bead <task-id> [--body <temporary-body>]
```

Do not hand-write a Conventional Commit subject. If subject generation fails, correct the task title or its
`dstack:commit:*` / `dstack:scope:*` labels.

Validation is mandatory and uses the repository's hk contract:

```bash
dstack check task --bead <task-id>
```

Fix every reported error. When the task intentionally requires no repository change, add a durable Beads note containing
exactly:

```text
No repository change: <specific reason>
```

Then rerun the check. Close the task only after it passes:

```bash
bd close <task-id> --reason 'Accepted outcome implemented and validated'
```

Implement one task by default. Continue only when the user explicitly requests all ready work. Never calculate fan-in or
advance the final audit yourself.
