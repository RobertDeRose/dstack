# Beads workflow conventions

Use Beads directly. Do not reimplement these operations in dstack.

## Setup

The target repository must contain the bundled formula source files. Do not
persist formula protos in the target database: their template steps and gates
pollute normal `bd ready` and `bd gate list` output. Validate with:

```bash
python3 "{baseDir}/../scripts/setup.py" doctor --root .
bd mol seed dstack-feature
bd mol seed dstack-project-alignment
```

`bd mol pour <formula-name>` cooks the installed formula inline. Persistent
protos are unnecessary for normal dstack use.

## Resolve a workflow root

An explicit Bead ID wins. Otherwise:

1. list candidate epic roots as JSON;
2. retain roots with the exact workflow label;
3. match the exact slug label first, then a unique case-insensitive title;
4. stop on zero or multiple matches.

Feature roots carry all feature-level identity and concrete metadata:

```text
workflow:feature
feature:<slug>
metadata.feature_slug=<slug>
metadata.base_branch=<branch>
metadata.design_path=<path>
```

Stable formula children carry only their static `dstack:step:*` label and
`metadata.dstack_step`. Do not duplicate templated feature variables into child
labels or metadata.

Audit roots carry audit-level identity and concrete audit metadata. Stable
alignment children likewise carry only static step identity; dynamic correction
tasks may carry `audit:<slug>` because dstack creates those tasks explicitly.

Do not maintain a hidden active-feature pointer.

## Resolve formula steps

Find direct children by their unique step labels:

```bash
bd list --parent <root-id> --all --label dstack:step:specification --json
bd list --parent <root-id> --all --label dstack:step:implementation-approval --json
bd list --parent <root-id> --all --label dstack:step:implementation --json
bd list --parent <root-id> --all --label dstack:step:closeout --json

bd list --parent <root-id> --all --label dstack:step:alignment-analysis --json
bd list --parent <root-id> --all --label dstack:step:alignment-approval --json
bd list --parent <root-id> --all --label dstack:step:alignment-corrections --json
bd list --parent <root-id> --all --label dstack:step:alignment-landing --json
```

Require exactly one direct child for each stable step. A missing or duplicate
step is a concrete workflow-integrity error; do not run migration automatically.

The implementation and corrections steps must remain epics. Their dynamic
children are the actual executable work. Do not change these container steps to
tasks merely to make a formula gate compile.

## Resolve the human gate

Use `bd gate list --json` and select the unique open human gate whose blocked
target is the relevant approval milestone:

- `dstack:step:implementation-approval` for a feature;
- `dstack:step:alignment-approval` for project alignment.

Never infer a gate ID from a title.

Beads 1.2.2 permits ordinary `blocks` dependencies only between like kinds:
task-to-task or epic-to-epic. Formula-generated gates are non-epic issues, so a
gate must block a task-sized approval milestone, not a workstream epic.

## Create dynamic work

Every dynamic implementation or corrective task must:

- be a child of the correct workstream epic;
- avoid inheriting the workstream's step label;
- carry its own work label;
- depend on the corresponding approval milestone;
- include a bounded outcome, evidence/context, acceptance criteria, and expected
  validation.

Representative feature command shape:

```bash
bd create "<title>" \
  --type task \
  --parent <implementation-epic-id> \
  --no-inherit-labels \
  --labels "dstack:work:implementation,feature:<slug>" \
  --deps <implementation-approval-id> \
  --description "<bounded outcome and context>" \
  --acceptance "<observable completion criteria>" \
  --json
```

For audit corrections, use the corrections epic as parent,
`dstack:work:alignment` plus `audit:<slug>` as labels, and the alignment-approval
milestone as the task dependency.

Do not pass a human gate ID to `--waits-for-gate`. In Beads, `--waits-for-gate`
only chooses the fan-in policy (`all-children` or `any-children`) for a separate
`--waits-for <spawner-id>` relationship. It is not an async-gate selector.
Formula-generated async approval is represented by the gated approval task.

Add dependencies among dynamic children only when execution genuinely requires
sequence. Unordered siblings are parallel in the Beads graph even when Phase 1
chooses to execute them serially.

## Approve a workflow stage

The formula-generated gate blocks the approval milestone. The explicit dstack
approval command performs this sequence:

```bash
bd gate resolve <gate-id> --json
bd update <approval-step-id> --claim --json
bd comments add <approval-step-id> -f <approval-summary.md>
bd close <approval-step-id> --reason "Approved by explicit dstack command" --json
```

The approval step also depends on specification/analysis, so it cannot be
claimed before the preceding planning step closes. Dynamic tasks depend on the
approval step and become ready only after that milestone closes.

If the gate was already resolved but the approval step remains open after an
interruption, resume by claiming and closing the existing approval step. Do not
create another gate or approval issue.

## Execute native ready work

Use the workstream molecule, not a dstack selector or scheduler:

```bash
bd ready --mol <workstream-epic-id> --exclude-type epic --claim --json
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
4. let the formula's closeout/landing step enter the ready frontier through the
   approval dependency and native `children-of(...)` fan-in.

The poured molecule root remains open after its children finish. Close the root
only after actual delivery, not merely after preparation.

## Gates

- The feature human gate authorizes the implementation-approval milestone.
- The project-alignment human gate authorizes the alignment-approval milestone.
- Resolve a human gate only through the corresponding explicit dstack command.
- Use `gh:run`, `gh:pr`, or timer gates for real external waits. For a PR:

  ```bash
  bd gate create --type gh:pr --blocks <root-id> --await-id <pr-number> \
    --reason "Await merged delivery PR" --json
  ```
- Use `bd gate check` for automatic gates; do not poll CI or PR state in dstack.
- Ordinary review iterations are not gates.
