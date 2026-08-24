# Resolve remaining workflow authority findings

[Design record](design.md)

## Delivered capability

dStack now preserves content identity across interrupted design approval, keeps human-selected PR delivery authoritative
until explicit cancellation, reports post-delivery finalization failures without rewriting Git, verifies release of
raced native claims, and recovers closed-feature footer evidence from delivered target history. Operators also receive
an explicit exact-build PATH requirement for the supported Beads binary.

## User-visible behavior

Approval writes and verifies a pending digest before changing native specification, gate, or approval state. A retry may
converge only the same committed design; changed content or unidentified native closure fails closed. Implementation
becomes authorized only after the approved digest and native states agree and pending identity is absent.

Direct merge refuses an unsuperseded PR gate before Git mutation. Operators can explicitly cancel the dStack gate with a
reason, preserving a native nonblocking relationship for audit; this does not modify the GitHub pull request. If Beads
finalization fails after direct or PR delivery, the command reports the before/delivered/observed target heads, observed
root state, original error, and mutation uncertainty without attempting rollback.

Native-ready claims now cover feature specification and alignment analysis. Unexpected or raced claims are restored to
open and unassigned state and then reread for verification. A delivered feature remains auditable from the configured
target ref after its branch and worktree are removed.

## Architecture integration

The implementation preserves the established authority split. Beads remains the authority for approval gates,
dependencies, readiness, claims, ownership, and completion. Git remains the authority for committed design bytes, footer
relationships, reachability, and delivery. The controller derives current facts on every invocation and persists no
commit mapping, recovery packet, scheduler, or custom workflow state.

The pending design digest is temporary content identity at a nontransactional boundary rather than approval state.
PR-mode replacement uses native gate and dependency operations. Claim recovery uses the pinned binary's native update
and an authoritative reread. Delivered audit reuses the existing footer parser over reachable target history and filters
it to expected feature work.

## Design reconciliation

### Delivered as designed

- Two-phase design authorization persists pending identity before native closure, promotes only the matching digest, and
  keeps every partial state unauthorized.
- Reauthorization invalidates approved and pending identity before reopening the native authorization boundary.
- Direct merge checks active PR-gate authority before Git mutation; explicit, reasoned cancellation replaces the
  blocking edge with a native nonblocking relationship.
- Direct and PR finalization share partial-delivery reporting and never perform automatic Git recovery.
- One verified release helper restores status and ownership for unexpected implementation, lifecycle, and fan-in claims.
- Feature specification and alignment analysis use exact native-ready claiming.
- Closed-feature audit recovers expected specification, implementation, and closeout footers from the target ref after
  normal branch/worktree cleanup, honors no-repository-change work, and ignores unrelated history.
- Exact Beads build guidance names the tested literal version and the required mise/aqua-before-Homebrew PATH behavior.

### Intentional differences

Not applicable — implementation evidence confirmed the pinned native operations and no accepted behavior required
substitution.

### Deferred scope

- Broader semantic-version compatibility remains deferred until another Beads build passes both real-boundary scenarios.
- Target-history audit uses one full reachable-history scan; optimization is deferred until repository-scale measurement
  shows material cost.
- Automated recovery after partial delivery remains intentionally deferred to a separately authorized native Beads or
  Git action.

### Removed or rejected scope

No approved scope was removed. The implementation continues to reject custom workflow persistence, stored Git-SHA
mappings, silent PR-mode replacement, automatic Git rollback, and inferred authorization from closed native state.

## Documentation

### End user and operator

README and the delivery, recovery, CLI, and compatibility references document the exact supported Beads binary, PR-gate
merge refusal and cancellation, partial-delivery facts, manual recovery boundary, and delivered-history audit.

### Developer and reviewer

The architecture, feature lifecycle, committed-content decision, metadata reference, and controller tests document the
pending-versus-approved predicate, native claim-release postcondition, delivery authority transition, and stateless
target-history evidence derivation.

### Future auditor

The design and this reconciliation preserve the rejected alternatives and remaining limitations. Fast tests cover
injected approval, delivery, claim-release, and audit failures. Separate real-Beads scenarios retain evidence for pinned
binary behavior and the complete feature lifecycle.

## Validation and limitations

Release validation covers configuration parsing, Python compilation, Ruff, strict typing of shared audit types,
dependency audit, mdBook policy/build, the full fast suite with no skips, both real-Beads acceptance scenarios,
candidate diff/footer/path checks, repository integrity, bundle verification, and a clean clone. The real smoke scenario
requires a longer local timeout because its runtime is dominated by native Beads/Dolt operations.

Compatibility remains limited to `bd version 1.2.2 (6c124203e)`. Cancelling the dStack PR gate does not close or edit a
GitHub pull request. Partial delivery reports facts but performs no recovery. Delivered audit requires the configured
target ref and reports missing target or expected evidence as an issue.
