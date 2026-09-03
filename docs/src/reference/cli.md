# Command contracts

All successful commands emit compact JSON on stdout. Deterministic failures emit JSON on stderr and return `2`.
Structural plan/task/audit validation returns `4` when collected state violates policy.

## Formula

```text
dstack ctl formula install [--update]
dstack ctl formula check
```

These commands install and verify only the packaged dStack formula. Beads must already be initialized with native
`bd init`. dStack does not wrap Beads initialization, stealth mode, diagnostics, hooks, synchronization, or repair.

## Plan

```text
dstack ctl plan check <plan-bead>
```

Validates native design and acceptance fields. It does not close or mutate the Bead.

## Worktree

```text
dstack ctl worktree ensure <feature-or-descendant>
```

Derives `feat/<slug>` and the base branch from the feature root, creates the branch from that base when absent,
delegates worktree creation and inventory to `bd worktree`, and independently verifies Git repository identity,
ancestry, branch, path, and cleanliness.

## Git

```text
dstack ctl git commit --bead <task> [--body-file <path>]
dstack ctl git amend --bead <task> [--body-file <path>]
```

Derives the Conventional Commit subject from native task labels and title. The message contains exactly one
`Beads: <task>` footer. Implementation commits may not stage `.beads/` content.

## Evidence and task checks

```text
dstack ctl evidence commits --bead <id> --ref <ref-or-range>
dstack ctl task check <task>
```

Task checks derive the base and feature refs from Beads. They validate task structure, direct implementation-epic
membership, the approval dependency, the sole native audit fan-in, documentation impact, reachable commit evidence,
footer uniqueness, feature-worktree identity/cleanliness, and mandatory `hk check -a`. No agent-facing flag can replace
the validation command or select alternate evidence refs.

## Audit and docs

```text
dstack ctl audit evidence <feature> [--include-plan]
  [--include-task <id>] [--include-decision <id>]
  [--history-for <id>] [--include-commit-paths]
dstack ctl docs validate
```

Audit evidence is read-only, bounded by default, and runs project/documentation validation. It reports deterministic
check failures but does not decide whether semantic drift exists. The audit skill requests full content only for
specific discrepancies and records resulting work or human gates in Beads.
