# CLI reference

The `dstack` CLI performs deterministic repository setup, validation, Git operations, and feature-documentation
mechanics for the workflow commands.

Use the long option names shown here in documentation and examples. The CLI also accepts `-b` as shorthand for
`--bead`.

## Output and exit status

Operational commands write JSON to standard output. Validation and runtime errors write JSON to standard error.
Argument parsing, `--help`, and `--version` remain normal human-readable terminal output.

| Exit status | Meaning |
| --- | --- |
| `0` | The command completed successfully. |
| `4` | A deterministic check completed and found invalid feature, task, or documentation state. |
| `2` | Usage, environment, filesystem, Git, or Beads operation failed. |

Set `DSTACK_OUTPUT_FORMAT=pretty` when you want indented JSON while inspecting command output manually.

## `dstack install`

```text
dstack install [--agent-dir PATH]
```

Install or update dStack's five Pi workflow commands and their stage-specific skills. The default target is
`PI_CODING_AGENT_DIR` when set, otherwise `~/.pi/agent`.

Installation preflights every managed destination and restores replaced resources if an update fails. If rollback is
incomplete, the error reports the retained recovery-copy directory.

This command installs agent resources only. Repository policy is installed by `dstack init`.

## `dstack init`

```text
dstack init [--root PATH] [--update]
```

Set up dStack in a Git repository. The command initializes Beads when needed, installs the packaged feature formula and
`.beads/PRIME.md`, and validates the resulting repository-local policy.

Initialization is idempotent and does not create feature work. It refuses to replace an existing formula or
`.beads/PRIME.md` that differs from the package unless `--update` is supplied.

After initialization, review and commit the installed formula, then run `dstack check formula`.

## `dstack check formula`

```text
dstack check formula [--root PATH]
```

Verify that the repository's dStack formula and `.beads/PRIME.md` match the installed package and that the formula
matches committed `HEAD`. New feature planning requires this policy check to pass.

## `dstack check plan`

```text
dstack check plan --bead ID [--root PATH]
```

Validate the fixed plan step for a feature before review. `ID` may be the feature root or any issue inside that feature.
The check validates required Beads fields and the six publishable design sections; semantic questions and product
choices remain the responsibility of the planning/review workflow.

## `dstack check review`

```text
dstack check review --bead ID [--root PATH]
```

Validate the reviewed feature graph before human approval. `ID` may be the feature root or any issue inside that
feature.

The check verifies the plan, fixed lifecycle steps, implementation-task fields, approval dependencies, persistent close
blockers, and that implementation tasks are not ready before approval.

## `dstack check task`

```text
dstack check task --bead TASK [--root PATH]
```

Validate one implementation task and its Git evidence. The selected task itself is required; this is intentionally a
task-level command rather than a feature selector.

The check verifies task structure, approval and close dependencies, delivered-outcome notes, canonical commit ownership
and paths, and feature-worktree cleanliness. An intentional `No repository change:` task must own no canonical commit.

## `dstack check docs`

```text
dstack check docs --slug SLUG [--root PATH]
```

Validate one feature-documentation directory independently of Beads. This structural check uses the feature slug because
it can run without workflow state.

Target repositories still own their whole-book or project-specific documentation validation.

## `dstack check feature`

```text
dstack check feature --bead ID [--offset N] [--include-plan] [--require-docs] [--root PATH]
```

Validate a completed feature and collect bounded evidence for `/close-feature`. `ID` may be the feature root or any
issue
inside that feature.

The check validates all relevant task, Git, ownership, and feature-documentation evidence even when summary output is
paged. Use:

- `--include-plan` to include the already-loaded feature plan for semantic close review;
- `--require-docs` after documentation publication to require valid feature documentation and close ownership; and
- `--offset N` to page task, decision, gate, and commit summaries in groups of 100.

When a result includes `next_offset`, repeat the command with that value to read the next summary page. Use focused
Beads
and Git commands such as `bd show ... --include-comments --json`, `bd history ... --json`, and `git show` when deeper
detail is needed. dStack does not duplicate those detail interfaces.

## `dstack worktree`

```text
dstack worktree --bead ID [--root PATH]
```

Locate the registered `feat/<slug>` worktree for a feature or create it when absent. `ID` may be the feature root or any
issue inside that feature.

If Git has an interrupted native operation, the command returns `recovery_required` and the existing worktree path
without repairing it. Follow [Interrupted Skill Recovery](../recovery.md) before another mutating dStack command.

## `dstack commit`

```text
dstack commit --bead TASK [--root PATH]
```

Create or correct the canonical commit for one in-progress implementation task. Implementation notes become ordered
commit bullets, and the commit receives exactly one `Task:` ownership trailer.

A clean retry is a no-op when the canonical commit already matches. Unpublished corrections update only the owning task
commit and replay descendants; published or ambiguous ownership is never rewritten automatically.

## `dstack docs export-design`

```text
dstack docs export-design --bead ID [--scaffold] [--root PATH]
```

Export the reviewed feature design without rewriting its content. `ID` may be the feature root or any issue inside that
feature.

`--scaffold` creates only unambiguous missing index sections, the design include, and the `SUMMARY.md` link. Existing
prose and section order are preserved. Ambiguous structure must be repaired explicitly.

## `dstack docs commit`

```text
dstack docs commit --bead ID [--root PATH]
```

Commit validated feature documentation for close. `ID` may be the feature root or any issue inside that feature.

The command accepts only the feature-documentation directory and its `SUMMARY.md` entry. When the valid documentation is
already inherited unchanged from the base branch, it returns `mode: unchanged` with no new commit rather than creating
an empty documentation commit.

## Selector rules

Feature-level commands accept a feature root or any issue inside that feature:

```text
dstack check plan --bead ID
dstack check review --bead ID
dstack check feature --bead ID
dstack worktree --bead ID
dstack docs export-design --bead ID
dstack docs commit --bead ID
```

Task-level commands require the implementation task itself:

```text
dstack check task --bead TASK
dstack commit --bead TASK
```

`dstack check docs` is independent of Beads and therefore uses `--slug`.
