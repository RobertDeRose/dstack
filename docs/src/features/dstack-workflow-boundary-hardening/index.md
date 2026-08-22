# Workflow boundary hardening

[Design record](design.md)

## Delivered capability

Implementation completes only claimed ready tasks; closeout and delivery require separate explicit authority. Design
paths, documentation policy, delivery finalization, recovery, and fresh-session behavior are durable fail-closed
boundaries.

## User-visible behavior

Completing the last implementation task leaves the workstream and closeout open. Validation failures stop before
completion. Normal delivery rejects tracked Git mutation during Beads finalization and creates no bookkeeping commit.
Recovery requires a separate user-authorized Git operation.

See the [feature lifecycle](../../development/feature-lifecycle.md) and
[compatibility guidance](../../reference/compatibility.md).

## Architecture integration

The four-step molecule and native child fan-in remain unchanged. dStack derives continuation from Beads, Git, and
durable documentation without a handoff packet or session state.

## Design reconciliation

### Delivered as designed

Implementation/closeout authority, validation reporting, canonical design path, narrow documentation leakage checks,
delivery mutation detection, and explicit recovery boundaries were delivered.

### Intentional differences

Generic status vocabulary was allowed after the guard was narrowed to structured dStack bookkeeping. This avoids
treating legitimate domain prose as workflow state.

### Deferred scope

No automatic recovery lifecycle was added; standard Git remains the explicit recovery mechanism.

### Removed or rejected scope

The start-stage methodology and implicit workstream closure were removed from the public lifecycle.

## Documentation

- [Architecture](../../architecture/index.md)
- [Core principles](../../development/index.md)
- [Feature lifecycle](../../development/feature-lifecycle.md)

## Validation and limitations

Focused tests cover command stop boundaries, path safety, leakage matching, and Git mutation detection. Full/release
checks remain repository-specific and must actually execute before closeout.
