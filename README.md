# dstack

`dstack` is a small Pi workflow package that applies a software-engineering
methodology using Beads and Git rather than implementing another workflow
engine.

Phase 1 restores the original feature workflow and three-tier project-alignment
workflow. Beads owns their execution through formulas, poured molecules,
dependencies, gates, ready work, claims, TODOs, comments, and native worktrees.

## Responsibilities

- **Beads** owns workflow templates and instances, work, dependencies, gates,
  readiness, claims, comments, TODOs, and completion state.
- **Git** owns source, branches, commits, diffs, and delivery boundaries.
- **Repository documentation** owns intended and supported behavior.
- **dstack** owns the workflow policy, review rules, and one installation helper
  that installs and validates the bundled formula source.

There is no dstack task database, readiness engine, scheduler, approval state
machine, reviewer topology, migration system, or interaction ledger.

## Commands

The public commands are prompt aliases. Internal skills are namespaced as
`dstack-beads-*` so stale or unrelated user skills cannot shadow the package.

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

`/setup-project` installs two formula source files into the target repository:

- `dstack-feature`
- `dstack-project-alignment`

A feature molecule has this stable skeleton:

```text
specification
    ↓
implementation-approval task ← human gate
    ├── blocks each dynamic implementation task
    └── blocks closeout

implementation epic
    ├── dynamically created implementation task
    ├── dynamically created implementation task
    └── dynamically created implementation task

closeout waits for children-of(implementation)
```

A project-alignment molecule uses the same pattern around its three authority
tiers:

```text
analysis and plan
    ↓
alignment-approval task ← human gate
    ├── blocks each dynamic correction
    └── blocks landing

corrections epic
    ├── dynamically created correction
    └── dynamically created correction

landing waits for children-of(corrections)
```

The approval milestone is deliberately a task. Beads 1.2.2 permits ordinary
blocking dependencies only between like kinds, so a formula-generated gate
cannot block an epic directly. The workstream remains an epic so native
molecule progress, ready work, and dynamic-child fan-in remain intact.

The dynamic work is ordinary Beads work. Each task is a child of its workstream
epic and depends on the task-sized approval milestone. dstack uses
`bd ready --mol`, atomic claims, dependencies, gates, `bd mol progress`, and
`bd mol current` directly.

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

When upgrading from an older dstack installation, first inspect and archive stale
standalone skills that Pi auto-discovers from `~/.pi/agent/skills`:

```bash
python3 /path/to/dstack/scripts/cleanup-legacy-pi-skills.py
python3 /path/to/dstack/scripts/cleanup-legacy-pi-skills.py --apply
```

The script is a dry run by default and moves recognized dstack skill directories
to a timestamped backup instead of deleting them. Restart Pi or run `/reload`
afterward.

The command initializes Beads only because invoking setup explicitly authorizes
it. Existing different formula files are not overwritten unless the user runs:

```text
/setup-project --force
```

Older dstack releases persisted formula protos with `bd cook --persist`. Beads
then exposed those template steps and template gates in the normal ready and gate
views. Forced setup verifies that a same-named graph is entirely template-owned
before deleting it. It never deletes an ordinary same-named Bead.

## Formula installer

The setup command calls the only bundled executable helper:

```bash
python3 skills/dstack-beads-core/scripts/setup.py install --root . --init
python3 skills/dstack-beads-core/scripts/setup.py doctor --root .
```

The helper only:

1. verifies the Git root and Beads executable;
2. optionally initializes Beads;
3. installs both formulas in an isolated temporary Beads repository;
4. validates them with `bd formula show` and `bd mol seed`;
5. pours one temporary molecule from each formula to exercise real issue, gate,
   and dependency insertion;
6. installs the two formula source files in the target only after that preflight
   succeeds;
7. removes verified accidental template graphs from older dstack setup when
   `--force` is explicit;
8. verifies that the installed formulas remain directly pourable by name.

It does not persist protos in the target repository. `bd mol pour` cooks the
installed formula inline, so target-side `bd cook --persist` is unnecessary and
would pollute normal `bd ready` and `bd gate list` output.

It does not select, claim, execute, or close workflow work.

## Phase boundary

Phase 1 intentionally excludes expert meetings, messenger extensions,
codebase-memory-mcp, tuicr, review wisps, and parallel source mutation. Those
can be layered onto these native Beads workflows only after this foundation is
validated in real repositories.

## Development

```bash
python3 -m pytest
python3 -m py_compile skills/dstack-beads-core/scripts/setup.py
git diff --check
```
