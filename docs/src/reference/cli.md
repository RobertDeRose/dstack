# Command contracts

Agent-facing operational commands emit deterministic JSON on standard output. Runtime validation failures emit JSON
diagnostics on standard error and return a nonzero status. Top-level help, version, unknown-command, and argparse output
remains human-readable. TTY output uses Rich's pretty JSON renderer; redirected output remains compact.

The canonical command surface is:

```text
dstack init [--root PATH] [--update]
dstack install skills [--agent-dir PATH]
dstack install formula [--root PATH] [--update]
dstack check plan --bead ID [--root PATH]
dstack check task --bead ID [--root PATH]
dstack check docs [--root PATH]
dstack commit [-a|--amend] -b|--bead ID [--body FILE] [--root PATH]
dstack worktree -b|--bead ID [--root PATH]
dstack audit FEATURE [detail flags] [--root PATH]
```

Setup and deterministic checks do not create workflow issues. The workflow is activated only by an explicitly invoked
workflow skill or an explicit request to use dStack.

## Initialization and installation

`init` initializes a missing Beads workspace with `--skip-agents`, installs the packaged `dstack-feature` formula and
scoped `PRIME.md`, and validates the resulting contract. It is idempotent, does not create workflow issues, and refuses
to replace a different project formula or prime unless `--update` is explicitly supplied. Existing generic Beads
integrations are not removed.

```text
dstack install skills [--agent-dir PATH]
dstack install formula [--root PATH] [--update]
```

`install skills` installs or updates the four dStack skills and prompts under the configured Pi agent directory.
`install formula` installs or verifies the packaged formula and scoped prime in an already initialized Beads workspace.

## Checks and repository operations

```text
dstack check plan --bead <plan-bead>
dstack check task --bead <task>
dstack check docs

dstack worktree --bead <feature-or-descendant>
dstack commit --bead <task> [--body <path>]
dstack commit --amend --bead <task> [--body <path>]
```

Plan checks validate native plan fields. Task checks validate graph membership, approval dependencies, Git evidence,
worktree cleanliness, documentation impact, and `hk check -a`. Worktree checks derive `feat/<slug>` from the feature
root and verify its branch, path, repository, and base ancestry. Commit subjects come from task labels and titles; each
commit contains exactly one `Beads: <task>` footer. Use `--amend` to preserve the existing footer ownership.

## Audit

```text
dstack audit <feature> \
  [--include-plan] \
  [--include-task ID] \
  [--include-decision ID] \
  [--history-for ID] \
  [--include-commit-paths]
```

Repeat `--include-task`, `--include-decision`, and `--history-for` when needed. Audit evidence is bounded by default and
expands only explicitly requested details.
