---
dstack-managed: true
name: dstack-implement
description: "Claim and implement native ready work with deterministic worktree, commit, and evidence checks."
disable-model-invocation: true
---

# Implement

Run only when explicitly invoked. Beads is the next-work authority; do not maintain another task list or calculate
readiness.

## Work loop

1. Run `dstack worktree --bead <feature-or-descendant>` and enter the returned feature worktree.
2. Resolve the implementation epic by its fixed label.
3. Claim one task with:

```bash
bd ready --parent <implementation> --label dstack:work:implementation --claim --json
```

Read the claimed task, direct blockers, relevant decisions, and only the repository material needed for that outcome. If
nothing is ready, report native blockers. Never claim the final step as implementation work.

Implement the smallest complete accepted outcome. Add behavioral tests before production code when practical. Keep code,
tests, configuration, and existing current documentation aligned, but do not create or update
`docs/src/features/<slug>/`; `/close-feature` writes feature publication only after review passes.

Use native task notes as the execution record. After each meaningful delivered increment, append one concise, verb-led
fragment:

```bash
bd note <task> "Implementation: Add compact output"
```

Keep each fragment to one concrete change, preferably one line and no more than 96 characters. Omit articles,
transitions, filler, rationale, and unnecessary implementation detail. Only ordered `Implementation:` notes become
commit bullets; dStack strips surrounding whitespace and punctuation, then adds a dash-and-space prefix without
wrapping. Do not copy planned description or design prose into notes, and do not put `Task:` or `Beads:` ownership
footers in note text. For an intentional no-change outcome, use only `No repository change: <specific reason>`.

For ambiguity, comment on the task and ask rather than guessing. Separate significant work becomes a native task linked
with `discovered-from`.

## Commit and validate

Review the complete diff and stage only task-owned paths. Run:

```bash
dstack commit --bead <task>
dstack check task --bead <task>
```

The commit command first verifies that the current directory is the Beads-registered conventional feature worktree, then
derives `feat(<slug>): <task title>`, one bullet per ordered `Implementation:` note, and exactly one `Task: <task>`
trailer. It refuses repository-changing tasks without an implementation note; planned description and design are never
commit material. Notes and generated bodies are bounded, and ownership footer text in notes is rejected. `Beads:`
footers are not ownership evidence. On a reopened task with one reachable unpublished canonical commit, it creates and
autosquashes an amend fixup so stale subject and body text are replaced by the current canonical message. Resolve a
stopped rebase without discarding unrelated descendant work; never rewrite published or ambiguous history.

Run the target repository's documented project-validation contract separately. dStack does not impose hk or mdBook. For
an intentional no-change task, record `No repository change: <specific reason>` in native notes before checking.

Close the task only after all checks pass:

```bash
bd close <task> --reason 'Accepted outcome implemented and validated'
```

Implement one task by default. With explicit `--all`, repeat the native claim loop sequentially until no implementation
task is ready, then report blockers or `/close-feature <root>`.
