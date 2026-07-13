---
name: implement-feature
description: Implement or continue the next ready task in a reviewed Beads feature while keeping code, tests, documentation, evidence, and commits aligned. Use when asked to implement feature work after `start-feature` closes `spec-reconcile`.
metadata:
  version: "0.1.0"
allowed-tools: Read Glob Grep Edit Write Bash Task
---

# Purpose

Use this skill after `/start-feature` closes `spec-reconcile`. Accept the same human feature selectors as
`/start-feature`. Beads selects executable work; `design.md` supplies intended behavior and design constraints. Resolve
`<core-dir>` as the installed `../dstack-core` skill directory.

## Execution

## 1. Load Minimal Context

Run `bd prime`, then resolve the supplied feature selector. When the selector is omitted, infer it only from an active
`feat/<num>-<slug>` branch. If the current branch is not a feature branch, stop and require a selector rather than
choosing unrelated ready work:

```bash
branch=$(git branch --show-current)
feature_selector=${branch#feat/}  # only when branch matches feat/*
uv run <core-dir>/scripts/resolve-feature.py "<feature-selector>" --json
bd show <resolved-root-id> --json
```

Use the returned root ID only for Beads operations and the returned `<num>-<slug>` reference for worktree, reporting,
and continuation commands. Resolve the implementation coordinator from root metadata `implementation_id`. Query the
feature children only as a one-time metadata repair path. This keeps the normal context load independent of total
feature size and works for both molecules and migrated parent-child lifecycles. Activate and verify `feat/<num>-<slug>`.

Select a user-specified task or atomically claim the next ready child:

```bash
bd ready --parent <implementation-id> --claim --json
bd show <task-id> --json
```

Read structured metadata, scope, acceptance criteria, blockers, design references, documentation ownership, and
validation before loading more files. Read only the relevant design sections and reader-facing pages unless broader
context is required.

Legacy `tasks.md` files are migration input only. Never use them as live task state after Beads import.

## 2. Implement the Bounded Outcome

Implement the smallest complete change satisfying the selected task. Preserve the reviewed design and established
repository patterns. Keep code, tests, configuration, migrations, observability, failure behavior, and recovery within
the task boundary.

Update the exact reader-facing pages assigned to the task. Add other pages only when delivered behavior creates a
durable reader need. Register each new page in `docs/src/SUMMARY.md` in the same work unit. Keep internal `design.md`
out of the reader-facing book.

## 3. Validate and Review

Run task-specific validation, `uv run scripts/check-docs.py` when documentation changes, and repository-standard checks.
Launch an isolated review focused on correctness, security, maintainability, test adequacy, and compliance with the
selected task and design.

Resolve actionable findings. Record commands, outcomes, limitations, findings, and fixes:

```bash
bd update <task-id> --append-notes "Validation and review evidence: ..."
```

## 4. Commit and Close

Run `git status --short`; identify pre-existing or out-of-scope changes and exclude them from the task boundary.

When the task changes the repository:

1. commit the complete bounded outcome;
2. include the Beads task ID in the commit message;
3. capture the exact commit SHA with `git rev-parse HEAD`;
4. record that SHA in the task notes before closure.

```bash
commit_sha=$(git rev-parse HEAD)
bd update <task-id> --append-notes "Commit evidence: ${commit_sha}"
bd close <task-id> --reason "Acceptance criteria satisfied; commit ${commit_sha}"
```

When the task legitimately requires no repository change, verify that no intended task change is uncommitted and record
an exact reason before closure:

```bash
bd update <task-id> --append-notes "Commit evidence: no commit required — <specific reason>"
bd close <task-id> --reason "Acceptance criteria satisfied; no commit required — <specific reason>"
```

Do not close a task with a placeholder SHA, an omitted commit field, or the unexplained phrase `no commit required`.
Every closed implementation task must have either a real commit SHA or a specific no-commit justification.

Record out-of-scope discoveries with provenance:

```bash
bd create "<discovered work>" \
  --type task \
  --deps discovered-from:<task-id> \
  --json
```

Add a blocking edge only when the discovered issue is a true prerequisite for safe completion.

## 5. Complete the Implementation Coordinator

After all required children are closed or explicitly deferred, compare delivered behavior with `design.md`, run
implementation-level acceptance checks, record evidence, and close the implementation coordinator:

```bash
bd update <implementation-id> --append-notes "Implementation acceptance evidence: ..."
bd close <implementation-id> --reason "Required implementation work complete; acceptance verified"
```

Return the canonical feature reference and human name, feature/task IDs, worktree, changes, documentation updated,
validation, isolated review, commit SHA, discovered work, implementation progress, and the next ready lifecycle item.
Recommend subsequent invocations with the canonical feature reference rather than only a Beads hash.
