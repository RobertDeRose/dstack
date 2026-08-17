# dStack

`dStack` is a small Pi workflow package for software engineering with Beads and Git. It is policy plus stateless
automation—not another workflow engine.

## Architecture

```text
Pi command -> short skill -> engineering decisions -> stateless dstackctl -> Beads / Git
```

- **Beads** owns work, dependencies, gates, readiness, claims, and completion.
- **Git** owns code, tests, durable documentation, commits, and delivery.
- **Documentation** explains product/design intent and planned vs implemented behavior; it does not mirror execution
  state.
- **dstackctl** performs deterministic native transitions without storing state.
- **The agent** focuses on architecture, implementation, tests, documentation, review judgment, and user decisions.

See:

- [Core principles](docs/core-principles.md)
- [Architecture](docs/architecture.md)
- [Workflow reference](docs/workflow-reference.md)
- [Compatibility](docs/compatibility.md)
- [Testing](docs/testing.md)

## Git and Beads linkage

Git commits reference their work item with one rewrite-safe footer:

```text
Beads: <bead-id>
```

Beads never stores commit hashes. dStack audits the current reachable history by
searching these footers, so amend/rebase/cherry-pick operations need no Beads
remapping.

## Commands

```text
/setup-project [--force]
/plan-features
/adopt-feature <legacy-feature>
/start-feature [id|slug|title]
/review-feature-spec [feature]
/implement-feature [feature] [task|--all]
/close-feature [feature] [ready|pr|merge]

/project-alignment-review [scope]
/project-alignment-execute <audit> [task|--all]
/project-alignment-land <audit> [ready|pr|merge]
```

`/start-feature` makes its resolved feature the conversational default for the
next feature commands. No dStack state file is created.

## Minimal feature workflow

```text
specification -> gated approval -> dynamic implementation tasks -> closeout
```

The stable workflow is a Beads formula/molecule. Real implementation tasks are created under its implementation epic and
selected through native ready work.

Specification approval stores a digest of the accepted design contents—not a Git SHA. Implementation stops only when the
design contents drift.

## Documentation policy

Docs may say a feature is `planned`, `implemented`, or `deprecated`, and must
explain what it does, why, and how. They must not contain `in-progress`,
`delivery-ready`, Beads/gate IDs, branch names, commit hashes, agent ownership,
or next-command bookkeeping.

Any durable planned-to-implemented update belongs in the feature candidate. A
successful merge/PR finalizer changes Beads only and is forbidden from creating
a Git commit.

## Requirements

- Git
- Python 3.12+
- Pi
- Beads 1.2.2+ with formulas, molecules, gates, JSON output, atomic claims, and
  native worktree support

## Install

```bash
pi install /path/to/dstack
```

Reload Pi, then run in the target repository:

```text
/setup-project
```

Use `/setup-project --force` only to replace changed formula source or perform
explicit known legacy repair. It preserves local Beads runtime data and never
persists formula protos in the live ready frontier.

## Development

```bash
uv run pytest
```

The default uv development group installs pytest and PyYAML automatically.
Set `DSTACK_REAL_BD=/path/to/bd` to require the real-Beads integration suite.
