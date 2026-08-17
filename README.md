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
- **Repository documentation** explains intended/supported behavior and durable
  product/design context; it never mirrors workflow state.
- **dstack** owns workflow policy, review guidance, a formula setup helper, one
  rewrite-safe Git-evidence helper, and the compatibility skill for adopting
  active legacy features.

There is no dstack task database, readiness engine, scheduler, approval state
machine, reviewer topology, migration engine, or interaction ledger.

## Foundational boundaries

KISS and YAGNI apply to the workflow itself. dstack should make deterministic
mechanics boring and leave agent attention for engineering decisions.

- Beads answers: what work exists, what depends on what, what is ready, what was
  decided, and what validation/review is still pending.
- Git answers: what changed in source/docs and why.
- Documentation answers: how the product is designed and behaves.
- dstack scripts may automate deterministic checks/transitions, but dstack does
  not duplicate those systems into packets, ledgers, schedulers, or shadow state.

Git↔Beads linkage is deliberately one-way and rewrite-safe. Every workflow-created
commit has a `Beads: <id>` footer. Beads does not store commit hashes. Rewriting a
commit message therefore requires no Beads migration or remapping.

Lifecycle commands do not flip roadmap statuses, write Beads IDs into design
docs, or create post-merge bookkeeping commits.

## Commands

The public commands are prompt aliases. Internal skills are namespaced as
`dstack-beads-*` so stale or unrelated user skills cannot shadow the package.

After installing the Pi package and running `/setup-project` in a repository:

```text
/plan-features
/adopt-feature <legacy-feature>
/start-feature <feature>
/review-feature-spec [feature]
/implement-feature [feature] [task | --all]
/close-feature <feature> [ready | pr | merge]

/project-alignment-review [scope]
/project-alignment-execute <audit> [task | --all]
/project-alignment-land <audit> [ready | pr | merge]
```

`/start-feature` makes its resolved feature the active feature for the current Pi session, so the next `/review-feature-spec` and `/implement-feature` commands can omit the feature selector. Explicit selectors still override the default.

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
epic and depends on the task-sized approval milestone. Feature-level concrete
metadata lives on the molecule root; stable formula children carry only static
step identity so Beads formula-variable interpolation is not required in labels
or metadata. dstack uses
`bd ready --mol`, atomic claims, dependencies, gates, `bd mol progress`, and
`bd mol current` directly.

## Legacy feature adoption

`/adopt-feature <feature>` is the one-time compatibility path for a feature that
is already open under the old dstack lifecycle. It pours the current formula,
preserves completed work and Git history, recreates only real remaining
implementation tasks, carries closeout requirements forward, supersedes obsolete
workflow ceremony, and leaves the new specification gate open. It never creates
a migration database or rewrites source history.

Do not use it for merely planned backlog features or already-current dstack
molecules.

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
views. An early cleanup could delete only the roots and leave orphaned template
steps or gates. Forced setup scans Beads with templates and gates explicitly
included, verifies every artifact in dstack's reserved formula namespaces, and
removes the complete batch. It never deletes a non-template issue.

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
7. removes verified accidental template graphs, including orphaned steps and
   gates left after partial cleanup, when `--force` is explicit;
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
