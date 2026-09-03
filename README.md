<!-- rumdl-disable-file MD041 -->

<p align="center">
  <img src="docs/src/assets/img/dstack_logo.png" alt="dStack logo">
</p>

`dStack` is a deterministic control plane for software-engineering agents.

- **Beads** owns plans, decisions, tasks, dependencies, gates, claims, readiness, and completion.
- **Git** owns repository content, branches, worktrees, and history.
- **hk** runs the repository validation contract.
- **dStack skills** guide semantic planning, review, implementation, and audit.
- **`dstack ctl`** performs deterministic repository checks and mutations.

## Workflow

Each feature uses one native Beads molecule:

```text
plan -> review -> human approval -> implementation tasks -> audit
```

The implementation step is a structural epic. Review creates each implementation task with a native approval blocker,
and the audit waits for the implementation children through one native `children-of(implementation)` dependency.

The installed skills are:

```text
/plan-feature   Record a feature plan and its decisions in Beads
/review-plan    Review the plan and create implementation tasks
/implement      Claim and implement the next ready task
/audit-feature  Compare the delivered work with the approved intent
```

The workflow is opt-in. Only these commands, or an explicit request to use dStack, activate Beads tracking. An explicit
`dstack ctl` command may perform its documented mechanics but does not create issues. Ordinary requests do not run `bd`,
create Beads issues, or require Beads initialization.

## Install

Requirements: Git, `uv`, Python 3.14, Beads 1.2.2, hk, and mdBook 0.5.4.

```bash
uv tool install --python 3.14 /path/to/dstack
dstack install_skills
dstack init
```

`dstack init` initializes Beads with generic agent setup disabled, installs the dStack formula and scoped `bd prime`
instructions, and validates the resulting workspace. It is idempotent and does not create workflow issues. Existing
generic integrations are not removed automatically.

## Commands

```text
dstack init [--root PATH] [--update]
dstack ctl formula install [--update]
dstack ctl formula check
dstack ctl plan check <plan-bead>
dstack ctl worktree ensure <feature-or-descendant>
dstack ctl git commit --bead <task> [--body-file <path>]
dstack ctl git amend --bead <task> [--body-file <path>]
dstack ctl evidence commits --bead <task> --ref <range>
dstack ctl task check <task>
dstack ctl audit evidence <feature> [detail flags]
dstack ctl docs validate
```

All successful commands emit compact JSON. Deterministic failures emit JSON diagnostics and a nonzero status. Beads
commands remain the authority for workflow transitions; dStack only validates or performs the mechanics required by the
skills.

## Documentation

The canonical documentation is the mdBook under `docs/`. It describes the current architecture, workflow, operations,
security boundaries, command contracts, and environment. `dstack ctl formula install` also installs the scoped
`.beads/PRIME.md` instructions.

## Development

```bash
uv run pytest                 # parallel by default (`-n auto`)
uv run pytest tests/acceptance
hk check -a
```

Use `-n 0` for a serial pytest run. Acceptance tests require Beads 1.2.2 on `PATH`.
