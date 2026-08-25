# Complete dStack workflow authority, adoption, and recovery hardening

> **Historical record:** setup/migration behavior described below reflects the workflow at the time this feature was
> delivered. It is superseded by the current
> [compatibility and formula-audit contract](../../reference/compatibility.md): formulas are templates, historical
> graphs are not migrated, and formula-contract drift is handled by semantic audit.

[Design record](design.md)

## Delivered capability

The accepted hardening work is implemented across the workflow controller, native Beads transitions, Git delivery
boundaries, setup, documentation migration, and operator references. The feature now binds authorization to exact
content and native relationships, preserves recovery evidence, and keeps Beads, Git, and mdBook as separate authorities.

## User-visible behavior

- Alignment approval and reauthorization fail closed when the reviewed plan, immutable audit input, terminal state, task
  graph, or native ownership changes.
- Legacy adoption validates the complete descendant classification before mutation, translates supported native
  relationships in memory, and records replacement history through native supersession only.
- Unqualified implementation claims accept the task selected by Beads' atomic operation, including a valid race winner;
  mismatches are released and verified.
- Failed delivery worktree cleanup retains the path and Git evidence needed for recovery instead of deleting potentially
  useful state.
- Closed-feature audits read documentation and footer evidence from one delivered revision rather than mixing the caller
  checkout with target history.
- Setup review/apply uses a strict canonical `dstack.setup-plan/v2` mutation object and digest. Drift in Beads,
  filesystem, formulas, navigation, or initialization state requires a new review.
- Setup doctor has explicit merge and PR profiles. Documentation migration stays conservative, reports ambiguous
  placement, and converges after manual repair.
- Abandoned PR-gate cancellation validates only the native recovery boundary and does not require a valid or mutable
  candidate.

## Architecture integration

Beads remains authoritative for lifecycle state, readiness, ownership, relationships, and supersession. Git remains
authoritative for durable source, documentation, delivered revisions, worktrees, and one-way footer evidence.
`dstackctl` performs deterministic, stateless coordination by rereading those native authorities; it adds no database,
shadow graph, migration map, scheduler, or commit ledger. mdBook remains the documentation renderer and policy boundary.

The implementation keeps the established four-stage lifecycle and formula skeleton. Content digests identify reviewed
bytes across non-transactional native mutations; they are not alternate workflow state or Git identities.

## Design reconciliation

### Delivered as designed

The implementation covers the accepted alignment authorization and terminal safety predicates, closed-world adoption,
atomic claiming, retained delivery recovery, immutable delivered-revision auditing, exact setup mutation planning,
explicit delivery profiles, conservative documentation migration, and candidate-independent PR-gate cancellation. Each
boundary has focused behavior coverage and the real native scenarios required by the design.

The documentation impact surfaces are reconciled in the operator CLI, delivery/recovery, compatibility,
development/tooling, architecture, lifecycle, and feature-record pages. The implementation preserves the supported Beads
build, mdBook version, public command names, native readiness, and Beads/Git separation.

### Intentional differences

Setup initialization lets native Beads create its own version-specific ignore file, then applies the reviewed dStack
ignore suffix without overwriting native content. Formula replacement also binds the reviewed destination preimage, so a
change after review cannot be silently replaced. These are narrower fail-closed preconditions than the original sketch
and preserve the same exact-plan contract.

### Deferred scope

No accepted product requirement is deferred. PR delivery and remote GitHub operations remain explicitly
capability-gated; merge-mode operation does not require a remote or GitHub CLI. Semantic placement of ambiguous legacy
Markdown remains a human decision rather than an automated feature.

### Removed or rejected scope

No duplicate dStack state, persisted migration map, Git-to-Beads commit mapping, workflow scheduler, readiness cache,
reviewer topology, or post-delivery bookkeeping was added. The implementation does not guess document placement or
rewrite Git after delivery or cleanup failure.

## Documentation

### End user and operator

Reader-facing behavior is documented in the command, compatibility, delivery, recovery, and development/tooling
references. Those pages describe explicit profiles, review digests, recovery evidence, migration ambiguity, native gate
cancellation, and retry boundaries without embedding transient workflow state.

### Developer and reviewer

Architecture and lifecycle guidance explain authority ownership, immutable revision evidence, exact setup mutation
identity, native relationship handling, and conservative documentation migration. Tests exercise externally meaningful
success, drift, race, rollback, cleanup, and recovery behavior.

### Future auditor

This record distinguishes accepted intent from delivered behavior and identifies where each authority is read. Audit
evidence remains reconstructible from native Beads and reachable Git history; no snapshot or commit mapping is
persisted.

## Validation and limitations

The completed validation set passed at the delivered candidate:

- all fast tests;
- all real-boundary acceptance scenarios;
- Ruff and Python compilation;
- documentation policy validation;
- `git diff --check`; and
- `git fsck --full`.

Validation covers the pinned Beads and mdBook boundaries used by the repository. PR-specific checks additionally require
a compatible remote and authenticated GitHub CLI; that environmental prerequisite does not weaken merge-mode health or
Beads-only recovery behavior.
