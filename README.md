<!-- rumdl-disable-file MD041 -->

<p align="center">
  <img src="docs/src/assets/img/dstack_logo.png" alt="dStack logo">
</p>

`dStack` is a deterministic control plane for software-engineering agents.

- **Beads** owns plans, decisions, tasks, dependencies, gates, claims, readiness, and completion.
- **Git** owns repository content, branches, worktrees, and history.
- **hk** runs the repository validation contract.
- **dStack skills** guide semantic planning, review, implementation, and audit.
- **dStack commands** perform deterministic repository checks and mutations.

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

The workflow is opt-in. Only the targeted skills, or an explicit request to use dStack, activate Beads tracking. dStack
setup and check commands perform their documented mechanics but do not create workflow issues. Ordinary requests do not
run `bd`, create Beads issues, or require Beads initialization.

## Install

Requirements: Git, `uv`, Python 3.14, Beads 1.2.2, hk, and mdBook 0.5.4.

```bash
uv tool install --python 3.14 /path/to/dstack
dstack install skills
dstack init
```

`dstack init` preflights the supported Beads version, initializes Beads with generic agent and hook setup disabled,
installs the dStack formula and scoped `bd prime` instructions, and validates the resulting workspace. It is idempotent
and does not create workflow issues. Existing generic integrations are not removed automatically, and an unhealthy
existing `.beads` workspace is reported rather than replaced. Review and commit the installed formula, then run
`dstack check formula`; commands that pour new feature work require this committed-policy check to pass.

## Commands

```text
dstack init [--root PATH] [--update]
dstack install skills [--agent-dir PATH]
dstack check formula [--root PATH]
dstack check plan --bead <plan>
dstack check review --bead <feature-root>
dstack check task --bead <task>
dstack check docs --feature <slug> [--root PATH]
dstack docs export-design --feature <feature-root> [--root PATH]
dstack commit --bead <task> [--body <path>]
dstack commit --amend --bead <task> [--body <path>]
dstack worktree --bead <feature-or-descendant>
dstack audit <feature> [detail flags]
```

Agent-facing operational commands emit deterministic JSON. Top-level help, version, unknown-command, and argparse output
remains human-readable. Beads commands remain the authority for workflow transitions; dStack only validates or performs
the mechanics required by the skills.

## Documentation

The canonical documentation is the mdBook under `docs/`. It describes the current architecture, workflow, operations,
security boundaries, command contracts, and environment. `dstack init` installs the scoped `.beads/PRIME.md`
instructions together with the project formula.

## Development

```bash
uv run pytest                 # parallel by default (`-n auto`)
uv run pytest tests/acceptance
hk check -a
```

Use `-n 0` for a serial pytest run. Acceptance tests require Beads 1.2.2 on `PATH`.
