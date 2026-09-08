---
dstack-managed: true
name: dstack-implement
description: "Claim and implement native ready work with deterministic worktree, commit, and evidence checks."
disable-model-invocation: true
---

# Implement

Run only when explicitly invoked. Beads is the next-work authority; do not maintain another task list or calculate
readiness.

## Start or resume

Run `dstack worktree --bead <feature-or-descendant>` and enter the returned worktree. A `recovery_required` result
locates interrupted work; it does not authorize edits or another commit. Inspect `git status` and deliberately finish
or abort the native Git operation before claiming work. Preserve existing edits and staged content and establish their
ownership. One agent writes a feature worktree at a time; the CLI's short mutation lock does not protect concurrent
editing or staging. Do not claim more work while another writer owns this worktree.

Resolve the implementation epic and inspect native position with `bd mol current <root> --json`. For a large graph,
use `bd mol progress <root> --json` and the focused in-progress query instead of loading every step:

```bash
bd list --parent <implementation> --status in_progress --label dstack:work:implementation --limit 0 --json
```

Resume the explicitly selected task, or the one in-progress task owned by this agent. Never steal another assignee's
claim or infer completion from an empty ready queue. If ownership is ambiguous, report the candidates. For a closed
selected task, verify its result and stop rather than claiming unrelated work. For an explicitly selected open task,
resolve its canonical ID, confirm it appears in the native ready results, then claim that exact ID with
`bd update <task> --claim --json`; do not substitute another task. Report native blockers if it is not ready.
Only when no task was selected and no task should be resumed, claim one native ready task:

```bash
bd ready --parent <implementation> --label dstack:work:implementation --claim --json
bd show <task> --include-comments --json
```

Read the selected task's description, design, acceptance, notes, and review comments even on resume. Read relevant
accepted decisions and direct blocker details only as needed. If nothing is ready, report native blockers using
`bd ready --parent <implementation> --label dstack:work:implementation --explain --json`. Never claim the final step.

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
commit bullets; dStack trims surrounding whitespace only, preserves technical punctuation, and adds a dash-and-space prefix without
wrapping. Do not copy planned description or design prose into notes, and do not put `Task:` or `Beads:` ownership
footers in note text. For an intentional no-change outcome, use only `No repository change: <specific reason>`.

Notes describe the current delivered outcome, not a growing correction history. On rework, preserve still-true bullets
and replace obsolete ones through native `bd update --notes`; keep review findings and correction rationale in comments.
Keep durable repository rationale in linked decision Beads. Do not duplicate these sources in a second log.

For ambiguity, comment on the task and ask rather than guessing. Separate significant work becomes a native task linked
with `discovered-from`.

## Commit and validate

Run the repository's documented project validation before committing. Review the complete diff, then stage only
task-owned paths. A resumed task may already have its canonical commit; a clean retry is safe. Run:

```bash
dstack commit --bead <task>
dstack check task --bead <task>
```

The commit command first verifies that the current directory is the Beads-registered conventional feature worktree, then
derives `<type>(<slug>): <task title>` (`feat` by default; an optional conventional prefix in the native title selects
`fix`, `refactor`, or another supported type), one bullet per ordered `Implementation:` note, and exactly one `Task: <task>`
trailer. It refuses repository-changing tasks without an implementation note; planned description and design are never
commit material. Notes and generated bodies are bounded, and ownership footer text in notes is rejected. `Beads:`
footers are not ownership evidence. On a reopened task with one reachable unpublished canonical commit, it rewrites only that owning commit and replays descendants without autosquashing unrelated fixups. With no staged
changes, an unchanged message is a no-op and changed notes/title reword the commit. A stopped rebase remains native Git
state: inspect `git status` and use `git rebase --continue` or `--abort`, not another dStack commit invocation. After
abort, inspect the retained correction commit before retrying; never rewrite published or ambiguous history.

dStack does not impose hk or mdBook. For an intentional no-change task, skip the commit command and record `No repository change: <specific reason>` in native notes before checking.

Close the task only after all checks pass:

```bash
bd close <task> --reason 'Accepted outcome implemented and validated'
```

Implement one task by default. With explicit `--all`, repeat this native resume/claim procedure sequentially until no implementation
task is ready, then report blockers or `/close-feature <root>`.
