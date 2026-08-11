# Migration artifact retirement

## Delivery Summary

- Beads feature root: `dstack-mol-b8d`
- Status: delivery-ready
- Pull request: not created
- Merge commit: pending fast-forward delivery
- Design record: [design.md](design.md)

## Delivered Capability

`/migrate-workflow` now treats `migration/delivered-record-candidates/` as transient local review material. Durable
migration authority and audit artifacts remain committed, while reviewed delivered-record candidates stay out of
ordinary checkpoints and can be removed only after final verification and explicit user approval.

## User-Facing Behavior

Finalization rejects missing, changed, or unsafe reviewed candidates before setting `migration_finalized`. Losing a
candidate before finalization invalidates its review metadata and requires fresh semantic review. A finalized migration
continues to verify after intentional candidate cleanup, and drafting is rejected for finalized manifests. Migration
checkpoint examples stage durable paths explicitly, handle optional resume approvals, and include tracked and untracked
adoption files without staging delivered candidates. Candidate drafting and adoption staging reject existing or dangling
symlinks at the candidate directory and feature-slug path.

## Design Integration

The implementation preserves the existing manifest, Beads state, committed checkpoints, and session authority as
migration evidence. It adds no new authority, state machine, journal, compatibility command, or Git-history lookup.
Delivered candidates remain a review workspace; template-adoption candidates retain their separate disposition
procedure.

## Operational Impact

Operators must keep delivered candidates out of commits and must not remove them before successful `finalize --apply`,
completed `verify --beads` with `migration_finalized: true`, and explicit approval. After approved cleanup, rerun
verification. If candidates disappear before finalization, redraft and semantically review them again.

## Reference and Contracts

- [Workflow architecture](../../architecture/index.md)
- [Migration operations](../../operations/index.md)
- [Development and validation](../../development/index.md)
- [Repository and migration reference](../../reference/index.md)
- `skills/migrate-workflow/SKILL.md`
- `skills/migrate-workflow/references/MIGRATION.md`

## Validation Evidence

- `mise run check`: passed at implementation commit `5b051f58ae92df543ee90d9cf8760bec2e495f8d`.
- `mise run docs:check`: passed on the close-out worktree (mdBook build and documentation checker).
- `uv run --no-project python scripts/check-docs.py`: passed.
- Focused migration behavior tests: 6 passed, including candidate symlink rejection.
- Adoption staging and migration contract tests: 4 passed, including dangling-symlink rejection.
- Ruff check and format checks passed for changed Python files.
- The full repository suite reached 225 passed before three unrelated baseline failures in generated GitHub Pages
  deployment assertions; no feature file was involved in those failures.
- Final task review approved the implementation after the staging-contract test correction.

## Design Reconciliation

### Delivered as Designed

Transient candidate classification, explicit durable staging, pre-finalization presence and digest checks, review
invalidation after candidate loss, finalized verification after approved cleanup, finalized-draft rejection, and the
single-task implementation boundary match the reviewed design.

### Intentional Changes

The reviewed design retains manual cleanup rather than adding an automatic deletion command or retirement journal. The
feature is delivery-ready pending the authorized fast-forward merge and post-merge record finalization.

### Deferred Work

Post-merge reconciliation records the actual merge SHA, changes this record and roadmap state to delivered, and closes
the delivery lifecycle. No implementation work remains deferred.

### Rejected or Removed Scope

Candidate dispositions, historical Git-blob proof, retirement journals, a compatibility command, and a new migration
workflow were explicitly removed from the earlier superseded design.

## Documentation Updated

- `docs/src/features/migration-artifact-retirement/design.md`
- `docs/src/operations/index.md`
- `docs/src/reference/index.md`
- `skills/migrate-workflow/SKILL.md`
- `skills/migrate-workflow/references/MIGRATION.md`
- `docs/src/features/migration-artifact-retirement/index.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`
- `docs/src/planned-features.md`

## Audit Trail

- Reviewed specification and graph reconciliation: `977701d256312f54ed75b24b458031bb67182e61`.
- Implementation and regression tests: `5b051f58ae92df543ee90d9cf8760bec2e495f8d`.
- Implementation task: `dstack-mol-u15.1`; coordinator: `dstack-mol-u15`.
- Architecture, simplicity, documentation, and execution reviews approved the redesigned boundary.
- Final task review approved the implementation after one contract-test finding was resolved.
- Delivery remains pending until the requested fast-forward merge and guarded post-merge finalizer complete.
