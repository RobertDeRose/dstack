# Improve workflow reviews

## Delivery Summary

- Beads feature root: `dstack-mol-2s9`
- Status: delivered
- Pull request: not created
- Merge commit: `78ce464dc0d769e9e7f1061fc8a114c81f507822` (fast-forward)
- Design record: [design.md](design.md)

## Delivered Capability

dstack review workflows now implement finite, bounded, recoverable direct specialist reviews on the feature branch.
Beads is the workflow manifest and durable review authority; the controller derives transient role assignments from
Beads, design/docs, and a pinned Git source boundary. The earlier packet-based implementation remains historical
evidence. Focused close-out validation completed, both specialized close reviewers approved the final source boundary,
and the structural aggregate authorized delivery.

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
scope. Direct cmux child-pane orchestration remains optional presentation integration. The redesigned close reviewers
approved the delivered boundary.

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
specialized reviewers. The redesigned close boundary required both implementation-integrity and delivery-integrity
approval before delivery.

## Audit Trail

Before publication, 66 local development commits were consolidated into focused commits: planning at `24031c7`, direct
review design at `9568fe7`, finite review state at `a3390c8`, topology migration at `c129bb1`, specialist roles at
`89dfc03`, controller orchestration at `3a616ec`, and documentation reconciliation at `78ce464`. The feature tree and
review diff digest remained byte-identical across the rewrite. The executable aggregate rebound both specialist
approvals to `78ce464` without invalidation. Superseded packet-era evidence, redesign findings, self-hosting decisions,
cutover verification, and validation evidence remain append-only in Beads.
