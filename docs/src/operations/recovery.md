# Recovery

Recover each authority from its native tool.

## Beads

```bash
bd where --json
bd status --json
bd ping --json
bd blocked --parent <feature-root> --json
bd history <bead> --json
```

Inspect and release claims, correct relationships, and resolve gates with native Beads commands.

## Worktrees

```bash
bd worktree list --json
git worktree list --porcelain
```

`dstack worktree --bead <feature-or-descendant>` verifies the registered worktree path, branch, repository, and ancestry
before returning success.

## dStack contract

The project formula and scoped Beads prime are installed as `.beads/formulas/dstack-feature.formula.toml` and
`.beads/PRIME.md`. Run `dstack init` only when the Beads workspace is missing. A failed native `bd where` with an
existing `.beads` path is treated as unhealthy and returned unchanged for deliberate recovery. For a healthy existing
workspace, use the lower-level commands:

```bash
# Missing workspace
dstack init

# Existing workspace
dstack install formula --update
dstack check formula
```

Review and commit the formula diff before using it for feature work. Do not delete, replace, or silently reinitialize an
ambiguous workspace; inspect the native Beads error and ask whether to recover or restart.

## Git evidence

`dstack check task --bead <task>` requires the task to be `in_progress` and validates exactly one reachable canonical
commit with a `Task: <task>` trailer and the deterministic `feat(<slug>): <task title>` subject. Its body must contain
one unwrapped bullet per ordered `Implementation:` fragment. Each fragment is concise, verb-led, one line, and no more
than 96 characters; formatting strips surrounding whitespace and punctuation before adding `- `. Planned description and
design prose are never evidence. A repository-changing task without an implementation note fails. `Beads: <task>` footers
are not ownership evidence.

For a reopened task with one unpublished canonical commit, append notes for the correction, stage only the correction,
and run `dstack commit --bead <task>` again. dStack creates an amend fixup, regenerates the complete subject and body
from the current task title and ordered notes, and immediately autosquashes from the feature base. If Git stops on a
conflict, retain unrelated valid descendant work, resolve deliberately, and continue the native rebase. Abort rather
than guess. Published or ambiguous history is never rewritten automatically.
