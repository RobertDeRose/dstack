# Command contracts

Successful commands emit compact JSON on standard output. Deterministic failures emit JSON diagnostics on standard error
and return a nonzero status.

## Initialization

```text
dstack init [--root PATH] [--update]
```

`init` initializes a missing Beads workspace with `--skip-agents`, installs the packaged `dstack-feature` formula and
scoped `PRIME.md`, and validates the resulting contract. It is idempotent, does not create workflow issues, and refuses
to replace a different project formula or prime unless `--update` is explicitly supplied. Existing generic Beads
integrations are not removed.

## Formula

```text
dstack ctl formula install [--update]
dstack ctl formula check
```

These lower-level commands install or verify the packaged formula and scoped prime in an already initialized Beads
workspace.

## Plan and worktree

```text
dstack ctl plan check <plan-bead>
dstack ctl worktree ensure <feature-or-descendant>
```

Plan checks validate native plan fields. Worktree checks derive `feat/<slug>` from the feature root and verify its
branch, path, repository, and base ancestry.

## Git and evidence

```text
dstack ctl git commit --bead <task> [--body-file <path>]
dstack ctl git amend --bead <task> [--body-file <path>]
dstack ctl evidence commits --bead <id> --ref <ref-or-range>
```

Commit subjects come from task labels and titles. Each generated commit contains exactly one `Beads: <task>` footer.

## Task and audit

```text
dstack ctl task check <task>
dstack ctl audit evidence <feature> [detail flags]
```

Task checks validate graph membership, approval dependencies, Git evidence, worktree cleanliness, documentation impact,
and `hk check -a`. Audit evidence is bounded by default and expands only the requested Beads, history, or commit paths.

## Documentation

```text
dstack ctl docs validate
```

Documentation validation checks the mdBook source, navigation, local links, decision records, and build output.
