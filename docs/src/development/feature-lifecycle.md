# Feature lifecycle

## Native molecule

`dstack-feature` is a persistent Beads formula with five fixed steps:

```text
plan -> review -> approval -> implementation -> audit
```

Approval has a native human gate. The implementation step is an epic containing
dynamic tasks. The audit uses formula fan-in and each reviewed task also has an
explicit native blocker to the audit.

## Planning

`/plan-feature` pours one molecule and records stable feature identity on its
root. The skill inspects only relevant code, tests, current docs, and decision
Beads. It classifies uncertainties and asks material questions one at a time.
The plan is stored in the plan Bead's native design field; acceptance criteria
use the native acceptance field.

The plan cannot close until `dstack ctl plan check` confirms required sections,
paired question/answer entries (or an evidence-based
`No material questions: <reason>` declaration), acceptance criteria, and all
three documentation audiences.

## Review and approval

`/review-plan` independently compares the plan with repository reality. Clear
local defects are corrected. Ambiguous authority is returned to the user.
Material durable choices are decision Beads.

Review creates bounded implementation tasks under the implementation epic. A
task is blocked by approval and explicitly blocks audit. Task-to-task dependencies
are added only when execution order is real.

The review step closes when the plan and task graph are coherent. The approval
gate is resolved only after explicit user approval; the approval task history is
the authorization record. dStack does not maintain pending/approved digests or a
parallel approval state machine.

## Implementation

`/implement` asks native Beads for one ready implementation task and claims it.
The skill reads that task, direct blockers, referenced decisions, and only the
repository sections needed for the accepted outcome.

The task includes code, tests, configuration, and current documentation. Staged
changes are committed through `dstack ctl git commit`, then checked with
`dstack ctl task check --run-validation` before native closure.

## Audit

`/audit-feature` claims the audit only when Beads exposes it. dStack gathers
compact facts; the skill performs semantic comparison.

Clear drift becomes ordinary remediation work that blocks audit. When it is
unclear whether approved intent, code, or documentation is correct, the skill
creates a native human gate and asks one targeted question. No correction ledger
or reconciliation document is required.
