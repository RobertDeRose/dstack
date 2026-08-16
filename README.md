# dstack

`dstack` is a small Pi workflow package that applies a software-engineering
methodology using Beads and Git rather than implementing another workflow
engine.

Phase 1 restores the original feature workflow and three-tier project-alignment
workflow. Beads owns their execution through formulas, protos, molecules,
dependencies, gates, ready work, claims, TODOs, comments, and native worktrees.

## Responsibilities

- **Beads** owns workflow templates and instances, work, dependencies, gates,
  readiness, claims, comments, TODOs, and completion state.
- **Git** owns source, branches, commits, diffs, and delivery boundaries.
- **Repository documentation** owns intended and supported behavior.
- **dstack** owns the workflow policy, review rules, and one installation helper
  that copies and cooks the bundled formulas.

There is no dstack task database, readiness engine, scheduler, approval state
machine, reviewer topology, migration system, or interaction ledger.

## Commands

After installing the Pi package and running `/setup-project` in a repository:

```text
/plan-features
/start-feature <feature>
/review-feature-spec <feature>
/implement-feature <feature> [task | --all]
/close-feature <feature> [ready | pr | merge]

/project-alignment-review [scope]
/project-alignment-execute <audit> [task | --all]
/project-alignment-land <audit> [ready | pr | merge]
```

## Native Beads workflows

`/setup-project` installs and cooks two formulas into the target repository:

- `dstack-feature`
- `dstack-project-alignment`

A feature molecule has this stable skeleton:

```text
specification
    ↓
human approval gate
    ↓
implementation epic
    ├── dynamically created implementation task
    ├── dynamically created implementation task
    └── dynamically created implementation task
    ↓
closeout waits for the implementation children
```

A project-alignment molecule has the same native structure around its three
authority tiers:

```text
analysis and plan
    ↓
human approval gate
    ↓
corrective-work epic
    ├── dynamically created correction
    └── dynamically created correction
    ↓
validation and landing waits for the correction children
```

The dynamic work is ordinary Beads work. dstack uses `bd ready --mol`, atomic
claims, dependencies, gates, `bd mol progress`, and `bd mol current` directly.

## Discovery policy

- Fix a clear in-scope issue within the current task.
- Capture a small incidental follow-up with `bd todo add` and link it with
  `discovered-from`.
- Create a fully specified task or bug for significant durable work.
- Use a nonblocking relation for context that should not affect readiness.

## Review policy

A workflow invocation authorizes an initial independent review and one
verification review after corrections. If another review is needed, dstack asks
the user. Explicit authorization always permits that review; there is no pass
cap.

A new defect or missing test is `changes requested`. It is a design decision
only when accepted product or architecture intent must change. Reviewer
infrastructure failure is `review unavailable`. External validation blocks only
the stage where it is genuinely required.

## Requirements

- Git
- Python 3.12 or newer
- Pi
- Beads with formulas, molecules, gates, TODOs, JSON output, atomic claims, and
  native worktree support

## Install

```bash
pi install /path/to/dstack
```

Restart Pi or run `/reload`, then invoke this from the target Git repository:

```text
/setup-project
```

The command initializes Beads only because invoking setup explicitly authorizes
it. Existing different formula files are not overwritten unless the user runs:

```text
/setup-project --force
```

## Formula installer

The setup command calls the only bundled executable helper:

```bash
python3 skills/dstack-core/scripts/setup.py install --root . --init
python3 skills/dstack-core/scripts/setup.py doctor --root .
```

The helper only:

1. verifies the Git root and Beads executable;
2. optionally initializes Beads;
3. installs the two formula source files;
4. validates them through `bd formula show`;
5. persists their protos through `bd cook --persist`;
6. verifies that `bd mol seed` can resolve them.

It does not create, select, claim, execute, or close workflow work.

## Phase boundary

Phase 1 intentionally excludes expert meetings, messenger extensions,
codebase-memory-mcp, tuicr, review wisps, and parallel source mutation. Those
can be layered onto these native Beads workflows only after this foundation is
validated in real repositories.

## Development

```bash
python3 -m pytest
python3 -m py_compile skills/dstack-core/scripts/setup.py
git diff --check
```
