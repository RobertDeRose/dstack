<!-- rumdl-disable-file MD041 -->

<p align="center">
  <img src="docs/src/assets/img/dstack_logo.png" alt="dstack logo">
</p>

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

- [Core principles](docs/src/development/index.md)
- [Architecture](docs/src/architecture/index.md)
- [Workflow reference](docs/src/development/feature-lifecycle.md)
- [Documentation](docs/src/development/documentation.md)
- [Compatibility](docs/src/reference/compatibility.md)
- [Testing](docs/src/development/tooling.md)

## Git and Beads linkage

Git commits reference their work item with one rewrite-safe footer:

```text
Beads: <bead-id>
```

Beads never stores task, implementation, delivery, evidence, or bookkeeping commit mappings. `dStack` audits current
reachable history through these footers, so amend/rebase/cherry-pick operations need no Beads remapping. Alignment plans
store reviewed findings and corrections only; they contain no Git baseline.

## Commands

```text
/plan-feature [id|slug|title|request]
/plan-features [deprecated alias]
/adopt-feature <legacy-feature>
/review-feature-spec [feature]
/implement-feature [feature] [task|--all]
/close-feature [feature] [ready|pr|merge]

/project-alignment-review [scope]
/project-alignment-execute <audit> [task|--all]
/project-alignment-land <audit> [ready|pr|merge]
```

The four feature stages follow the decisions being made:

- `/plan-feature` discovers what to build and why, then preserves complete planned intent in Beads without changing Git.
- `/review-feature-spec` materializes that intent as the canonical design, reconciles it with the repository, builds the
  implementation graph, and asks for authorization.
- `/implement-feature` implements only authorized outcomes in code and tests; durable documentation waits for closeout.
- `/close-feature` performs the one final reconciliation of intent, implementation, tests, documentation, and delivery.

`/plan-features` is a deprecated thin alias to `/plan-feature`; it has no separate behavior.

## Minimal feature workflow

```text
specification -> gated approval -> dynamic implementation tasks -> closeout
```

The stable workflow is a Beads formula/molecule. Real implementation tasks are created under its implementation epic and
selected through native ready work.

Specification approval stores a digest of the accepted design contents—not a Git SHA. Implementation stops only when the
design contents drift.

## Documentation policy

mdBook is canonical for managed projects. The specification-review boundary creates only the missing core foundation
when a feature first needs durable design documentation; `docs/src/SUMMARY.md` remains the sole navigation manifest and
optional sections follow actual reader needs.
The same durable book serves users/operators, developers/reviewers, and future agents/auditors.

Docs may say a feature is `planned`, `implemented`, or `deprecated`, and must explain what it does, why, and how. They
must not contain `in-progress`, `delivery-ready`, Beads/gate IDs, branch names, commit hashes, agent ownership, or
next-command bookkeeping.

Accepted feature intent remains in `design.md`; closeout performs the one final reconciliation in `index.md` and
updates authoritative current-product documentation. Implementation tasks do not create documentation or reconciliation
work. A candidate may be fixed up or rebased before delivery while retaining linear terminal evidence.
A successful merge/PR finalizer changes Beads only and is forbidden from creating a Git commit.

## Requirements

- Git
- Pi
- mise
- Python 3.14, mdBook 0.5.3, and Beads 1.2.2 exactly, as pinned by this package.

The bundled launcher invokes every dStack Python entry point in a package-relative locked runtime selected from
`mise.toml` and `mise.lock`. Prepare it once with `mise --cd <dstack-package-root> install --locked`. `bd --version`
must print `bd version 1.2.2 (6c124203e)`. An ambient Homebrew `bd` is never selected and remains outside the tested
compatibility boundary. Direct Python execution of controller entry points is rejected; invoke `bin/dstack` or the
installed Pi commands.

## Install

```bash
pi install /path/to/dstack
```

Reload Pi and use the normal workflow commands in the target repository. The controller automatically initializes Beads
when needed and uses packaged dStack formulas as authority before workflow operations. Native pours use the packaged
formula transiently; legacy tracked formula copies are tolerated and restored unchanged, so an upgrade does not create a
formula-migration or commit boundary.

Formula versions are semantic planning/review contract versions, not package versions. Existing approved work keeps its
historical shape. When an active feature was last reviewed against an older formula contract, the controller requests an
internal semantic specification audit exactly once. If the existing approved design and tasks already satisfy the current
contract, dStack records the current audited version and continues. If a material task/design delta is required, the agent
presents only that delta and requires renewed user approval before changing approved work.

## Development

```bash
uv run pytest
```

The default uv development group installs pytest and PyYAML automatically. Real-Beads acceptance runs separately and
fails when `bd` is unavailable:

```bash
uv run pytest tests/acceptance
```

CI runs the fast suite and each real-Beads scenario as separate required jobs.
