# Test and mechanical-layer hardening

[Design record](design.md)

## Delivered capability

The controller uses a protocol-only fast test double for dStack-owned command construction and isolated real-Beads
scenarios for native lifecycle behavior. Mechanical commands expose useful help, bound subprocess work, and preserve the
single stateless controller entry point.

## User-visible behavior

Fast tests complete quickly without invoking Beads. Required real-Beads acceptance fails rather than skips when the
supported binary is unavailable. Public command help explains inputs and mutation/failure boundaries.

See [testing dStack](../../development/tooling.md).

## Architecture integration

Beads remains the authority for readiness, gates, ownership, dependencies, and fan-in. Git tests use real temporary
repositories. Request-local read reuse does not survive a controller invocation.

## Design reconciliation

### Delivered as designed

The stateful fake lifecycle was replaced with declared protocol snapshots, the controller was split behind its stable
executable, command help was completed, and subprocess-heavy evidence reads were bounded.

### Intentional differences

Release acceptance was kept to two real-boundary scenarios: one Beads contract and one end-to-end feature smoke path.
This is smaller than a broad scenario matrix while covering the supported authority boundaries.

### Deferred scope

Additional real-Beads scenarios are deferred until a distinct unsupported boundary appears.

### Removed or rejected scope

No fake readiness engine, plugin registry, dependency-injection framework, persistent cache, or coverage-percentage gate
was retained.

## Documentation

- [Architecture](../../architecture/index.md)
- [Testing](../../development/tooling.md)
- [Feature lifecycle](../../development/feature-lifecycle.md)

## Validation and limitations

Fast tests are not evidence for native Beads semantics. The two acceptance scenarios require the pinned real binary and
are the release authority for that boundary.
