# Feature lifecycle

## Native molecule

`dstack-feature` is a persistent Beads formula with five fixed steps:

```text
plan -> review -> approval -> implementation -> audit
```

Approval has a native human gate. The implementation step is a structural epic containing dynamic tasks. It has no
blocking dependency on the task-shaped approval milestone because Beads 1.2.2 rejects task/epic `blocks` edges. Each
reviewed child task is created atomically with a direct dependency on approval. The audit has one native
`children-of(implementation)` waits-for edge as its sole implementation fan-in.

## Planning

`/plan-feature` verifies native Beads initialization, installs the dStack formula, pours one molecule, and records one
`feature:<slug>` identity label plus base-branch metadata on its root. The skill inspects only relevant code, tests,
current docs, and decision Beads. It classifies uncertainties and asks material questions one at a time. The plan is
stored in the plan Bead's native design field; acceptance criteria use the native acceptance field.

The plan cannot close until `dstack ctl plan check` confirms required sections, paired question/answer entries (or an
evidence-based `No material questions: <reason>` declaration), acceptance criteria, and all three documentation
audiences.

## Review and approval

`/review-plan` independently compares the plan with repository reality. Clear local defects are corrected. Ambiguous
authority is returned to the user. Material durable choices are decision Beads.

Review creates each bounded implementation task and its approval dependency in one native `bd create` operation. The
command disables parent-label inheritance so concrete work cannot masquerade as the structural implementation step.
Task-to-task dependencies are added only when execution order is real. Direct task-to-audit blockers are prohibited.

The review step closes when the plan and native task graph are coherent. The approval gate is resolved only after
explicit user approval; the approval task history is the authorization record. dStack does not maintain pending/approved
digests or a parallel approval state machine.

## Implementation

`/implement` asks native Beads for one ready implementation task and claims it. The skill reads that task, direct
blockers, referenced decisions, and only repository sections needed for the accepted outcome.

The task includes code, tests, configuration, and current documentation. Staged changes are committed through
`dstack ctl git commit`, then checked with `dstack ctl task check` before native closure. Task checks derive the feature
refs from Beads, validate native graph membership, run `hk check -a`, and reject a dirty feature worktree.

## Audit

`/audit-feature` claims the audit only when Beads exposes it. The claim itself is the native fan-in proof; the skill
does not recalculate child completion.

`dstack ctl audit evidence` runs deterministic validation and returns a bounded index. The skill asks for full plan,
task, decision, history, or commit-path content only when a concrete discrepancy requires it. Clear drift becomes
ordinary remediation work under the implementation epic. Ambiguous authority becomes a native human gate and one user
question. No correction ledger or reconciliation document is required.
