# dStack Beads context

This project uses Beads for the explicitly activated dStack feature workflow.

## Scope

The dStack workflow is opt-in. The presence of `.beads`, installed skills, this file, or `bd` does not activate task
tracking.

- For an ordinary request, do not run `bd` or create, update, claim, or close Beads issues.
- `/plan-feature`, `/review-plan`, `/implement`, and `/audit-feature` activate the workflow.
- An explicit request to use dStack also activates the workflow.
- An explicit `dstack ctl` command may perform its documented mechanics but does not create workflow issues.

Do not install or enable generic Beads agent instructions or session hooks for this project. `bd prime` is context only;
it does not activate the workflow and should not run as a generic session hook.

## Active dStack workflow

Once activated, Beads owns plans, decisions, tasks, dependencies, gates, claims, readiness, and completion. Git owns
repository content, branches, worktrees, and history. Do not infer readiness, maintain a task list, or create a second
workflow state store.

Use the native Beads queue and the dStack skills:

```bash
bd ready --json
bd show <id> --json
bd update <id> --claim
bd close <id> --reason '<reason>'
```

The dStack skills scope queue queries to the active feature molecule and label. Do not claim unrelated ready work.

Use `dstack ctl` for deterministic formula, worktree, commit, evidence, task, and documentation checks. During
implementation, use `dstack ctl git commit --bead <task>` rather than hand-writing the task commit subject. Run the
repository validation contract before closing active work.

Do not use Markdown TODO lists, readiness caches, handoff ledgers, commit-to-task maps, or other shadow workflow state.
Use `bd remember` only for durable project memory that belongs in Beads; ordinary implementation notes belong in the
repository or the active task.

## Active-work completion

For an active dStack task, validate the complete outcome, review the diff, and close only the claimed native task after
its checks pass. Do not apply the generic Beads session-close rule to ordinary requests: ordinary requests have no Beads
task to close.
