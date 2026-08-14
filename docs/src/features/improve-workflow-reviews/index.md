# Improve workflow reviews

## Delivery Summary

- Beads feature root: `dstack-mol-2s9`
- Status: close review verification in progress — delivery blocked
- Pull request: not created
- Merge commit: not applicable before approval
- Design record: [design.md](design.md)

## Delivered Capability

dstack review workflows now implement finite, bounded, recoverable direct specialist reviews on the feature branch.
Beads is the workflow manifest and durable review authority; the controller derives transient role assignments from
Beads, design/docs, and a pinned Git source boundary. The earlier packet-based implementation remains historical
evidence. Focused close-out validation is complete, implementation integrity is provisionally approved, and the
delivery-integrity finding is entering verification. Delivery remains blocked pending structural aggregate approval.

## User-Facing Behavior

- Reviewers use nicobailon/pi-subagents with a 600,000 ms whole-run deadline, fresh isolated context, read-only
  acceptance, and only read-only tools. Persisted session/output artifacts and bounded wait/status results are
  completion authority; quiet tool calls and terminal panes are not failure or approval evidence.
- Start reviews use specification-clarity and execution-readiness roles. Task work receives one focused task reviewer.
  Close-out launches implementation-integrity and delivery-integrity reviewers concurrently.
- Implementation integrity reviews correct code behavior, quality and simplicity, security, and maintainability.
  Delivery integrity reviews documentation, validation evidence, Beads state, implemented records, roadmap/navigation,
  delivery claims, and drift.
- Review state supports one initial pass and one verification pass, binds each state to its owning Beads issue and
  immutable Git source boundary, preserves resolved decisions, and requires a new committed design boundary for
  redesign. Aggregate reconciliation invalidates overlaps without opening a third pass.
- The collector subagent, shared content packet, and union-of-review-inputs flow are removed; reviewers inspect their
  assigned paths directly.
- Existing review graphs migrate from the canonical primary worktree under the Beads lease. Old evidence remains
  attributable, old approval does not transfer, and stale controllers fail closed after the cutover marker.

## Design Integration

Beads remains the authority for lifecycle state, dependencies, review findings, validation evidence, and delivery state.
The controller owns transient assignment derivation and reviewer launch; reviewers are read-only and never wait for a
collector or another role. The topology migrator remains the single leased graph-mutation owner. The redesigned boundary
keeps parallel task execution in the dependent `parallel-feature-execution` feature and defers workflow-level budget
overrides.

## Operational Impact

Operators can diagnose deadline, incomplete-review, replacement, redesign, waiver, and migration stops from durable
state, the owning Beads review issue, saved run artifacts, and telemetry. Historical packet identities remain
audit-only. A topology migration must run from the canonical primary worktree; busy leases, changed snapshots, malformed
graphs, and failed verification stop before incomplete delivery. Append-only review notes and claimed active reviewer
tasks remain valid during cutover verification. Interrupted migration can retry from its immutable plan before the
cutover marker, while a completed marker is verified as an idempotent no-op.

## Reference and Contracts

- [Workflow architecture](../../architecture/index.md)
- [Install and use dstack](../../operations/index.md)
- [Developing dstack](../../development/index.md)
- [Feature lifecycle](../../development/feature-lifecycle.md)
- [Repository and command reference](../../reference/index.md)
- `skills/dstack-core/references/REVIEW-STATE.md`
- `skills/dstack-core/references/REVIEW-FINDINGS.md`
- `skills/dstack-core/assets/pi-reviewers/` and the pinned `nicobailon/pi-subagents` package
- `skills/dstack-core/references/PI-REVIEWER-ROSTER.md`
- `skills/dstack-core/scripts/migrate-review-topology.py`

## Validation Evidence

- Historical packet remediation validation remains recorded in Beads and prior commits; it does not validate this
  redesign boundary.
- Focused implementation validation passed for reviewer-state/aggregate contracts, direct reviewer assets, topology
  migration, packet-provider retirement, generated guidance, and documentation checks. Close-out revalidates this
  focused set before review. The full repository suite remains intentionally excluded.

## Design Reconciliation

### Current Redesign Boundary

Finite reviewer budgets, executable two-pass review state, bounded redesign transitions, narrow reviewer capabilities,
explicit decision handling, focused task validation, and old-graph migration remain retained intent. Deterministic
packet construction and one holistic close review are historical implementation choices being replaced by direct
specialized reviewers. The self-hosting cutover was applied to the earlier boundary from the canonical primary worktree
with no approval transfer.

### Intentional Changes

The topology migrator uses separate create, parent, and dependency commands because the supported Beads CLI rejects
explicit issue IDs combined with parent flags and interprets creation-time blocker flags in the opposite direction from
these prerequisites. The migrator repairs reversed prerequisite edges from the earlier self-hosting cutover, accepts
append-only audit notes and claimed active review tasks during verification, and regression coverage models these
contracts.

### Deferred Work

Workflow-level reviewer-budget overrides and parallel implementation workers remain deferred to their respective future
scope. Direct cmux child-pane orchestration remains optional presentation integration. Delivery remains blocked until
the redesigned close reviewers approve.

### Rejected or Removed Scope

The collector subagent, shared content packet, packet projections, temporary LLM context-builder topology, former
six-role review split, automatic full-suite lifecycle gates, and parallel worker orchestration are not part of the
redesigned boundary.

## Documentation Updated

- `AGENTS.md`
- `docs/src/SUMMARY.md`
- `docs/src/architecture/index.md`
- `docs/src/development/feature-lifecycle.md`
- `docs/src/development/index.md`
- `docs/src/features/improve-workflow-reviews/design.md`
- `docs/src/features/parallel-feature-execution/design.md`
- `docs/src/features/index.md`
- `docs/src/operations/index.md`
- `docs/src/planned-features.md`
- `docs/src/reference/index.md`
- `docs/research/pi-subagent-extension-alternatives.md`
- `skills/setup-project/template/AGENTS.md.jinja`
- `skills/setup-project/template/docs/src/development/feature-lifecycle.md.jinja`

## Close-out Remediation

The pre-delivery record is intentionally not a merge claim. Earlier packet-based holistic reviews preserved findings and
stopped without delivery. The attempted v15 rebuild then failed to materialize the required shared packet before review;
no approval or delivery action transferred. This redesign replaces that serialized collector flow with direct
specialized reviewers. The redesigned close boundary will require both implementation-integrity and delivery-integrity
approval before delivery.

## Audit Trail

The direct-review specification boundary was reconciled at `e0ddcf83673d530f3d333dee329090fac8c2ffb8`. Implementation
commits include `573b3b6`, `b9089ff`, `f742981`, `4330e45`, `88a4e92`, `b2937b0`, and the post-review safety fix
`234822d`. The earlier packet-based specification was reconciled at `9ee77611b5acd888aa4d11e5fdfb1bed225d35d0`; its
implementation commits are `0d8b8e0`, `b229dcc`, `f981ff5`, `4f8b407`, `1a975e2`, `5912837`, `1bf1e30`, and `7c9a3b6`;
compatibility fixes are `cd94df0` and `4acebc3`. The implementation coordinator `dstack-mol-wrq` and its final
focused-validation child closed at `4e6d4b8`. The old review records were preserved as superseded evidence, and no old
approval transferred. Close-out remediation commits remain historical evidence for the packet-based boundary. The
attempted v15 review never reached content review because the shared packet was not materialized; this redesign is the
next specification boundary. The self-hosting decision, installed reviewer boundary, cutover marker, migration repair,
and validation evidence remain in the feature root and close-out Beads records. The first direct close-review boundary
approved at `483a95d`; the later safety fixes overlapped both verified domains, invalidated that approval, and require
one fresh redesigned close-review boundary.
