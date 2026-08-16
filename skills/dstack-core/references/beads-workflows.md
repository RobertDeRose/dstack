# Beads workflow conventions

Use Beads directly. Do not reimplement these operations in dstack.

## Setup

The target repository must contain the bundled formulas and their persisted
protos. Validate with:

```bash
python3 "{baseDir}/../scripts/setup.py" doctor --root .
bd mol seed dstack-feature
bd mol seed dstack-project-alignment
```

## Resolve a workflow root

An explicit Bead ID wins. Otherwise:

1. list candidate epic roots as JSON;
2. retain roots with the exact workflow label;
3. match the exact slug label first, then a unique case-insensitive title;
4. stop on zero or multiple matches.

Feature roots carry:

```text
workflow:feature
feature:<slug>
```

Audit roots carry:

```text
workflow:project-alignment
audit:<slug>
```

Do not maintain a hidden active-feature pointer.

## Resolve formula steps

Find direct children by their unique step labels:

```bash
bd list --parent <root-id> --label dstack:step:specification --json
bd list --parent <root-id> --label dstack:step:implementation --json
bd list --parent <root-id> --label dstack:step:closeout --json

bd list --parent <root-id> --label dstack:step:alignment-analysis --json
bd list --parent <root-id> --label dstack:step:alignment-corrections --json
bd list --parent <root-id> --label dstack:step:alignment-landing --json
```

Require exactly one direct child for each stable step. A missing or duplicate
step is a concrete workflow-integrity error; do not run migration automatically.

## Resolve the human gate

Use `bd gate list --json` and select the unique open human gate whose waiter or
blocked target is the relevant workstream epic. Never infer a gate ID from a
title.

## Create dynamic work

Every dynamic implementation or corrective task must:

- be a child of the correct workstream epic;
- avoid inheriting the workstream's step label;
- carry its own work label;
- depend on the preceding analysis/specification step;
- wait on the workstream's human gate;
- include a bounded outcome, evidence/context, acceptance criteria, and expected
  validation.

Representative command shape:

```bash
bd create "<title>" \
  --type task \
  --parent <workstream-id> \
  --no-inherit-labels \
  --labels "dstack:work:implementation,feature:<slug>" \
  --deps <specification-id> \
  --waits-for-gate <gate-id> \
  --description "<bounded outcome and context>" \
  --acceptance "<observable completion criteria>" \
  --json
```

For audit corrections, use `dstack:work:alignment` and `audit:<slug>`.

Add dependencies among dynamic children only when execution genuinely requires
sequence. Unordered siblings are parallel in the Beads graph even when Phase 1
chooses to execute them serially.

## Execute native ready work

Use the workstream molecule, not a dstack selector or scheduler:

```bash
bd ready --mol <workstream-id> --exclude-type epic --claim --json
```

For a named task:

1. show it as JSON;
2. verify it is a descendant of the expected workstream;
3. verify it appears in the current ready set;
4. claim it atomically with `bd update <id> --claim`.

Use:

```bash
bd mol current <molecule-id> --json
bd mol progress <molecule-id> --json
```

for native workflow state and progress.

## Complete a workstream

Do not close a workstream epic while required children remain open. When all
required children are closed or explicitly deferred/accepted:

1. inspect `bd mol progress <workstream-id> --json`;
2. verify no required child remains open;
3. close the workstream epic;
4. let the formula's closeout/landing step enter the ready frontier through
   native dependencies and `children-of(...)` fan-in.

The poured molecule root remains open after its children finish. Close the root
only after actual delivery, not merely after preparation.

## Gates

- The feature human gate represents acceptance of the specification boundary.
- The project-alignment human gate represents approval of the Tier 1 plan.
- Resolve a human gate only through the corresponding explicit dstack command.
- Use `gh:run`, `gh:pr`, or timer gates for real external waits.
- Use `bd gate check` for automatic gates; do not poll CI or PR state in dstack.
- Ordinary review iterations are not gates.
