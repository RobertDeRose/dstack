# Controller correctness and auditability

[Design record](design.md)

## Delivered capability

dStack resolves feature identity explicitly, enforces approved-design content, uses native Beads ownership and
dependencies, and audits rewrite-safe Git footer evidence before completion and delivery.

## User-visible behavior

Feature commands fail closed for ambiguous selection, design drift, competing ownership, missing Git evidence, stale
targets, unsafe documentation paths, and non-fast-forward delivery. Intentional no-repository-change work requires a
durable reason rather than an evidence bypass.

See the [feature lifecycle](../../development/feature-lifecycle.md) and
[compatibility boundary](../../reference/compatibility.md).

## Architecture integration

The controller remains stateless. Beads owns work and native transitions; Git owns source, documentation, and delivery
evidence. Design approval is a content digest rather than a commit identity.

## Design reconciliation

### Delivered as designed

Selector, ownership, design-drift, footer-audit, delivery-target, path-safety, and no-Git-mutation boundaries were
delivered through the existing controller.

### Intentional differences

The canonical feature design path was narrowed to the mdBook source tree and the documentation guard was narrowed to
structured dStack bookkeeping so ordinary domain status language remains valid.

### Deferred scope

No controller database, reviewer topology, or Git-to-Beads mapping was added. Those rejected abstractions remain out of
scope.

### Removed or rejected scope

The ambiguous no-commit bypass was replaced by explicit no-repository-change completion with a reason.

## Documentation

- [Architecture](../../architecture/index.md)
- [Core principles](../../development/index.md)
- [Feature lifecycle](../../development/feature-lifecycle.md)

## Validation and limitations

Fast tests cover dStack-owned decisions and real-Beads acceptance covers native claims, gates, dependencies, fan-in, and
delivery. Active legacy workflows still require explicit adoption rather than normal command repair.
