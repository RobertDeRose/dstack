# Migration safety and clarity

## Delivery Summary

- Beads feature root: `dstack-mol-tki`
- Status: delivered
- Pull request: not created; delivered by local fast-forward merge
- Merge commit: `047bc5b2f2c4f496bc77c2f478d600ed15a6bbf9`
- Design record: [design.md](design.md)

## Delivered Capability

Legacy workflow migration now preserves project-owned hk behavior, classifies durable and temporary artifacts, explains
required decisions, uses verified project-local hooks, and resumes large Beads imports without replaying completed work.
Repository identity, default branches, delivered-record reconciliation, and migration progress are explicit and durable.

## User-Facing Behavior

Migration inventories existing hooks before adoption and blocks unapproved capability loss. Dry-run and apply are
separate; apply reports progress and stores resumable phases. Large imports use bounded Dolt commits. Canonical project
identity comes from repository evidence rather than a migration worktree suffix. Historical delivered records can be
drafted from legacy, Beads, and Git evidence, but verification and finalization require digest-bound human review.

## Design Integration

The implementation preserves Beads as live workflow authority, Copier as scaffold authority, project-owned files as
migration inputs, and ordinary verified Git commits as checkpoint authority. Migration-mode documentation validation is
strictly transitional; finalization restores the ordinary strict contract.

## Operational Impact

Operators receive actionable recovery for provisioning, hook, relationship, and documentation failures. Manifests retain
hook inventories, artifact dispositions, contextual decisions, import phases, progress, checkpoint evidence, canonical
identity, and delivered-record review state. Collaborative Beads initialization exposes control files and the formula
for the workflow-owned commit while keeping database contents in synchronized Dolt history.

## Reference and Contracts

- [Architecture](../../architecture/index.md)
- [Install and migration operations](../../operations/index.md)
- [Development and validation](../../development/index.md)
- [Repository and migration command reference](../../reference/index.md)

## Validation Evidence

- `uv run --frozen --group test pytest -q tests/test_repository.py::test_migration_safety_resumable_end_to_end`: passed.
- Migration test partition: 13 passed.
- `HK_JOBS=1 mise run check`: passed.
- `uv run --frozen --group test pytest`: 224 passed, 1 skipped.
- Final implementation reviewer: passed with no blockers.

## Design Reconciliation

### Delivered as Designed

Additive hk reconciliation, artifact lifecycle enforcement, contextual questions, verified checkpoints, resumable
imports, canonical repository identity, migration-safe documentation reconciliation, and final integration are
delivered.

### Intentional Changes

Production migration evidence expanded the reviewed design with checkbox-status correction, bounded Beads transactions,
progress reporting, canonical branch discovery, exact stealth tracking, navigation generation, and reviewed delivery
record drafting. Final integration composes bounded fixtures rather than duplicating expensive 300-record and
provisioner setup in one temporary repository.

### Deferred Work

None within the delivered feature scope.

### Rejected or Removed Scope

General Pkl AST merging, automatic acceptance of generated delivery records, broad hook bypass, and automatic deletion
of legacy archives remain intentionally unsupported.

## Documentation Updated

- `docs/src/architecture/index.md`
- `docs/src/operations/index.md`
- `docs/src/development/index.md`
- `docs/src/reference/index.md`
- `docs/src/features/migration-safety-and-clarity/design.md`
- `skills/migrate-workflow/SKILL.md`
- `skills/migrate-workflow/references/MIGRATION.md`

## Audit Trail

Implementation commits span `0de2faf` through `23f0a55`, with performance evidence in `a34574c` and design expansion in
`7affc7c`. Every bounded task received isolated review; the implementation coordinator `dstack-mol-9zl` closed after all
children passed focused and full validation.
