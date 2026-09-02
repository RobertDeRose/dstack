# Command contracts

All successful commands emit compact JSON on stdout. Deterministic failures emit JSON on stderr and return `2`.
Structural plan/task validation returns `4` when the inspected object is valid JSON but violates policy.

## Infrastructure

```text
dstack ctl infra install [--update-formula]
dstack ctl infra check
```

`install` initializes Beads when necessary and installs the packaged formula as project configuration. `check` validates
Beads compatibility, exact formula content, formula parsing, and reports native `bd doctor` output.

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
delegates worktree creation to `bd worktree`, and verifies shared repository identity and the conventional path.

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
dstack ctl task check <task> [--base <ref>] [--head <ref>] [--run-validation]
```

Task checks validate task structure, documentation impact, reachable commit evidence, footer uniqueness,
feature-worktree identity/cleanliness, and optional project validation.

## Audit and docs

```text
dstack ctl audit evidence <feature> [--include-history] [--run-validation]
dstack ctl docs validate
```

Audit evidence is read-only and intentionally does not decide whether semantic drift exists. The audit skill makes that
judgment and records resulting work or human gates in Beads.
