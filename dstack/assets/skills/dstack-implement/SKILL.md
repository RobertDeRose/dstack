---
dstack-managed: true
name: dstack-implement
description: "Resume or claim ready implementation work with deterministic worktree, commit, and evidence checks."
disable-model-invocation: true
---

# Implement

## dStack operations

Use these dStack commands in this stage:

```bash
dstack worktree --bead <feature-or-descendant>
dstack commit --bead <task>
dstack check task --bead <task>
```

Enter the worktree returned by `dstack worktree` before editing.

After a repository-changing task is implemented, validated, and staged, run `dstack commit`, then `dstack check task`.
For an intentional no-change task, record only `No repository change: <specific reason>`, skip `dstack commit`, and run
the task check.

Example after a completed increment:

```bash
bd note <task> "Implementation: Preserve inbound arrival timestamps"
dstack commit --bead <task>
dstack check task --bead <task>
```

A clean retry of `dstack commit` may return unchanged.

## Select work

Inspect workflow position with `bd mol current <root> --json`. For a large graph use `bd mol progress <root> --json` and a
focused in-progress query:

```bash
bd list --parent <implementation> --status in_progress --label dstack:work:implementation --limit 0 --json
```

Use the explicitly selected task when supplied. Otherwise continue the in-progress implementation task surfaced by the
query before claiming new ready work. A closed selected task is verified and reported; do not substitute unrelated work.

For an explicitly selected open task, resolve its canonical ID, confirm it is ready, then claim that exact ID:

```bash
bd update <task> --claim --json
```

Only when no task was selected and nothing should be resumed, claim one ready implementation task:

```bash
bd ready --parent <implementation> --label dstack:work:implementation --claim --json
bd show <task> --include-comments --json
```

If nothing is ready, report blockers with:

```bash
bd ready --parent <implementation> --label dstack:work:implementation --explain --json
```

Never claim the close step.

## Implement

Read the selected task's description, design, acceptance criteria, notes, and review comments on every resume. Read
relevant decisions and direct blockers only as needed. Implement the smallest complete accepted outcome. Add behavioral
tests before production code when practical, then run the repository's documented validation contract. Keep code, tests,
configuration, and existing current documentation aligned, but leave `docs/src/features/<slug>/` to `/close-feature`.

Use task notes as the delivered-outcome record. Append one concrete `Implementation:` fragment for each
meaningful completed increment. Keep it concise, preferably one line and no more than 96 characters. Do not copy planned
description/design prose into notes. On rework, preserve still-true fragments and replace obsolete ones through task
notes; keep review rationale in comments and durable rationale in linked decisions. Do not place `Task:` or `Beads:`
ownership footers in note text.

For ambiguity, comment on the task and ask rather than guessing. Separate significant work becomes a Beads task linked
with `discovered-from`.

## Finish

Review the complete diff and stage only task-owned paths before the dStack commit/check sequence. Close the task only
after the repository validation and `dstack check task` pass:

```bash
bd close <task> --reason 'Accepted outcome implemented and validated'
```

Implement one task by default. With explicit `--all`, repeat the same resume/claim procedure sequentially until no
implementation task is ready, then report blockers or `/close-feature <root>`.
