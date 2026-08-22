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

Beads never stores commit hashes. dStack audits the current reachable history by
searching these footers, so amend/rebase/cherry-pick operations need no Beads
remapping.

## Commands

```text
/setup-project [--force]
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
- `/implement-feature` implements only authorized outcomes.
- `/close-feature` reconciles intent, implementation, tests, documentation, and delivery.

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

mdBook is canonical for managed projects. Setup creates only the missing core foundation without overwriting project
content; `docs/src/SUMMARY.md` remains the sole navigation manifest and optional sections follow actual reader needs.
The same durable book serves users/operators, developers/reviewers, and future agents/auditors.

Docs may say a feature is `planned`, `implemented`, or `deprecated`, and must explain what it does, why, and how. They
must not contain `in-progress`, `delivery-ready`, Beads/gate IDs, branch names, commit hashes, agent ownership, or
next-command bookkeeping.

Any durable planned-to-implemented update belongs in the feature candidate. A
successful merge/PR finalizer changes Beads only and is forbidden from creating
a Git commit.

## Requirements

- Git
- Python 3.12+
- Pi
- mdBook on `PATH`
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

Setup creates and validates the canonical mdBook foundation without overwriting
existing pages or creating optional taxonomy. It preserves legitimate tracked
Beads repository configuration such as `.beads/config.yaml`,
`.beads/metadata.json`, `.beads/README.md`, and
`.beads/.gitignore`. It keeps `.beads/interactions.jsonl` local and untracked so
normal Beads transitions cannot dirty Git history.

Use `/setup-project --force` only to replace changed formula source or perform
explicit known legacy repair. It preserves local Beads/Dolt runtime data and
never persists formula protos in the live ready frontier. Review and commit the
repository setup boundary before starting feature work.

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
