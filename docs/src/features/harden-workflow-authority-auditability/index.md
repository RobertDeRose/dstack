# Harden workflow authority and auditability

[Design record](design.md)

## Delivered capability

dStack now enforces the Beads/Git authority split at each workflow transition. Open work is claimed through native
readiness, authorization is bound to the committed design and exact worktree, approved graphs require explicit
reauthorization before expansion, and terminal workflow roots stay open until confirmed delivery. PR-gate
classification, Git-ref validation, worktree validation, and completion evidence fail closed on ambiguous state.

Feature and alignment Markdown records now have one deterministic semantic contract. Current operator, recovery,
security, CLI, environment, metadata, compatibility, testing, and decision guidance is available in the canonical
mdBook. A read-only audit view joins current Beads, Git, and documentation facts without persisting a report or
Git-to-Beads mapping.

Setup now separates deterministic planning from digest-bound application, verifies postconditions, compensates
setup-owned resources when possible, and reports precise recovery otherwise. Doctor and CI expose the supported tool,
formula, documentation, native-behavior, and repository-integrity boundaries.

## User-visible behavior

Operators receive actionable refusals instead of guessed authority when a task is blocked or owned elsewhere, a design
or worktree is dirty, approved scope is changed, a Git ref is unsafe, or a PR gate conflicts. Retrying convergent
operations reuses the same native objects rather than duplicating gates or workflow state. Explicit reauthorization
invalidates prior approval before reopening the native authorization boundary.

Setup plan is read-only and stable for unchanged inputs. Apply requires the reviewed authority-state digest and a clean
unchanged precondition. Audit output is available as deterministic JSON or Markdown on standard output. No new
configuration knobs or persistent dStack state were added; the documented `DSTACK_COMMAND_TIMEOUT_SECONDS` override
remains the bounded-command control.

Existing active workflows are not rewritten. Their next guarded transition may surface previously tolerated ambiguous or
incomplete state, with explicit repair or supersession guidance. The supported boundary remains Beads 1.2.2, mdBook
0.5.3, and Python 3.13.

## Architecture integration

The implementation extends the existing stateless controller seams. Beads still owns hierarchy, blockers, gates,
readiness, claims, and completion. Git still owns accepted bytes, code, tests, documentation, evidence, ancestry, and
delivery. Repository documentation remains the durable product specification; agents retain engineering judgment.

Shared helpers are limited to invariants genuinely used by both feature and alignment paths: exact native task
transition, terminal-root preservation, record-contract validation, and authorization-boundary reopening. The audit and
setup plans are derived in memory for one invocation and are never written as a second authority. Compatibility behavior
is isolated with pinned-binary reproducers and retirement conditions.

## Design reconciliation

### Delivered as designed

All accepted authority boundaries were implemented: committed-content approval with digest-last ordering, native
exact-task claims, ownership verification, clean completion evidence, immutable approved scope, explicit
reauthorization, terminal roots preserved until delivery, conflict-safe PR gates, option-safe Git revisions, and
verified worktree identity and ancestry.

The semantic feature/alignment records, canonical operations and security handbook, bounded ADR set, stateless audit
output, plan/apply setup flow, expanded doctor, compatibility registry, and focused Python 3.13 release checks were also
delivered. The controller still contains no database, scheduler, packet protocol, task manifest, readiness calculation,
persistent audit cache, or Git-to-Beads SHA mapping.

### Intentional differences

Real Beads 1.2.2 testing established that unlike-kind blocking dependencies are rejected, so the formula's like-kind
approval milestone remains necessary. The same testing reproduced the dynamic-child fan-in gap; the narrow direct-child
negative safety veto therefore remains alongside native readiness.

Native reauthorization proved able to restore the exact authorization boundary under the pinned release, so the
implementation uses that path rather than requiring a superseding workflow. Static typing was intentionally confined to
concrete audit boundary views, and coverage is reported without a percentage gate.

### Deferred scope

Testing a future Beads or mdBook version is deferred to an explicit compatibility change with the same real-boundary
scenarios. Stable external CI artifact links are omitted because no retention guarantee is part of this repository.
GitHub network authorization is validated by delivery preflight and documented operator requirements rather than by a
credentialed integration test.

### Removed or rejected scope

The implementation rejected a second workflow store, transaction journal, approved-task manifest, custom readiness or
ownership engine, checked-in audit snapshot, subjective documentation scoring, repository-wide typed rewrite, file-size
refactor, and arbitrary coverage threshold. None was required to meet the accepted behavior.

## Documentation

### End user and operator

Current installation, defaults, daily use, cleanup, and concurrency guidance is in
[Operations](../../operations/index.md). Direct and PR delivery authority is in
[Delivery authority](../../operations/delivery.md); partial failures, rollback, backup/restore, and troubleshooting are
in [Recovery and troubleshooting](../../operations/recovery.md). Trust boundaries, privacy, redaction, and secrets
policy are in [Security](../../security/index.md).

### Developer and reviewer

Current state transitions and native-operation boundaries are in the
[feature lifecycle](../../development/feature-lifecycle.md). Semantic record rules are in
[Documentation](../../development/documentation.md), and validation ownership and release checks are in
[Testing](../../development/tooling.md). Command, environment, metadata, and compatibility contracts are under
[Reference](../../reference/index.md).

### Future auditor

The durable rationale is retained in this design and the [architecture decisions](../../decisions/index.md). The audit
command reconstructs live evidence on demand, while this record states delivered behavior, deviations, validation, and
limitations without mirroring transient workflow state.

## Validation and limitations

Validation completed on 2026-08-24 on macOS with `uv 0.11.7`, Python 3.13.13, `bd version 1.2.2 (6c124203e)`, mdBook
0.5.3, and Git 2.55.0. The following commands passed with no skipped required scenarios:

```bash
uv run pytest -q -rs --cov=skills/dstack-beads-core/scripts --cov-report=term
uv run pytest -q tests/acceptance/test_bd_contract.py
uv run pytest -q tests/acceptance/test_feature_smoke.py
uv run ruff check .
uv run mypy --strict skills/dstack-beads-core/scripts/dstack_types.py
uv run pip-audit
uv run python scripts/validate-config.py
uv run python -m compileall -q skills scripts tests
python3 skills/dstack-beads-core/scripts/dstackctl.py docs validate
git diff --check
git fsck
git bundle create <temporary-bundle> --all
git bundle verify <temporary-bundle>
```

The fast suite reported 77% aggregate coverage without enforcing a threshold. The real-Beads contract and end-to-end
smoke scenarios passed separately. A clean local clone also passed configuration parsing, Python compilation, clean
status, and mdBook validation. Bundle verification reported complete history; `git fsck` reported only unreachable
development objects and no corrupt or missing reachable objects.

No credentialed GitHub PR creation was performed, no alternate operating system was exercised locally, and no
unsupported tool release is claimed compatible. Direct delivery and PR finalization remain protected by their runtime
clean, ancestry, remote-base, and gate preflights. There are no known residual product or security findings within the
accepted scope.
