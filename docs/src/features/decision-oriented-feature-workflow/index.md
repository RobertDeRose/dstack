# Decision-oriented feature workflow

[Design record](design.md)

## Delivered capability

The public feature lifecycle now maps directly to four engineering decisions: plan intent, review and authorize
specification, implement authorized outcomes, and reconcile/deliver the completed feature.

## User-visible behavior

Planning writes complete durable intent to one Bead without changing Git. Specification review materializes the
repository-aware design and task graph, then asks for explicit authorization. Implementation completes only native ready
tasks. Closeout owns final reconciliation and delivery.

See the [feature lifecycle](../../development/feature-lifecycle.md).

## Architecture integration

The redesign reuses the stable four-step Beads molecule, stateless controller, registered worktree, approved-design
digest, native task dependencies, and rewrite-safe Git footers. No planning store or handoff protocol was introduced.

## Design reconciliation

### Delivered as designed

Lossless Beads-only planning, review-time materialization, outcome-oriented task creation, explicit authorization, and
four public stages were delivered.

### Intentional differences

The existing initialization and scaffold commands remain public mechanical CLI operations because review uses them, but
they are not separate Pi lifecycle stages.

### Deferred scope

The deprecated plural planning alias remains only as thin delegation while old invocations age out.

### Removed or rejected scope

The public start-feature prompt, skill, and methodology were removed. Planning creates no molecule, worktree, design
file, task, or Git commit.

## Documentation

- [Architecture](../../architecture/index.md)
- [Core principles](../../development/index.md)
- [Feature lifecycle](../../development/feature-lifecycle.md)

## Validation and limitations

Contract tests preserve the public command boundary and the real-Beads smoke scenario proves planning-to-delivery
behavior. Active legacy workflows still use explicit adoption rather than review-time repair.
