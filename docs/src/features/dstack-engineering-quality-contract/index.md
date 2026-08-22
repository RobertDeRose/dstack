# Engineering quality contract

[Design record](design.md)

## Delivered capability

Feature design and implementation guidance require explicit outcomes, non-goals, reuse, failure/security/compatibility
behavior, observable acceptance, behavior-first tests, and documentation impact before delivery.

## User-visible behavior

Specification review creates a missing design scaffold without overwriting existing work. Task creation rejects blank
acceptance criteria. Implementation and closeout stop when required validation is incomplete or weaker than the accepted
outcome.

See [core principles](../../development/index.md) and the
[feature lifecycle](../../development/feature-lifecycle.md).

## Architecture integration

The quality contract lives in durable documentation, short skills, fixed scaffolds, and behavioral tests. It adds no
scoring service, approval matrix, coverage gate, or workflow state.

## Design reconciliation

### Delivered as designed

The scaffold, acceptance-presence guard, behavior-first testing guidance, and three-audience documentation-impact
contract were delivered using existing controller and test patterns.

### Intentional differences

The scaffold remained intentionally mechanical: it checks presence and non-overwrite behavior while agents judge
semantic quality.

### Deferred scope

Semantic scoring and automated design grading remain deliberately deferred until a concrete need can justify them.

### Removed or rejected scope

Separate agent documentation and separate test-only/documentation-only workflow tasks were rejected as duplicate truth
and unnecessary ceremony.

## Documentation

- [Core principles](../../development/index.md)
- [Documentation conventions](../../development/documentation.md)
- [Testing](../../development/tooling.md)

## Validation and limitations

Fast tests prove scaffold idempotency, path refusal, task acceptance guards, and contract guidance. The agent remains
responsible for judging whether authored intent and acceptance are meaningful.
