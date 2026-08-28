# Safe forced setup migration and recovery

[Design record](design.md)

## Delivered capability

Forced setup is now a bounded migration boundary rather than an in-place best-effort repair. Planning validates the
projected repository, documentation tree, mdBook build, formulas, filesystem, and Beads topology before mutation. Apply
consumes the exact saved plan, isolates repository changes in a detached Git worktree, targets the contained Beads
runtime explicitly, and verifies a native Dolt backup before graph changes. Native backup restore and Git worktree
operations provide the recovery boundary for failed or interrupted migrations.

The execution path also reuses complete Beads inventories, focuses individual reads only when required core fields are
missing, groups identical supported multi-ID updates, keeps writes sequential, and reports invocation-local command
counts and phase timings. It adds no persistent migration database, journal, manifest, or Beads-to-Git mapping.

## User-visible behavior

`setup plan --force` remains read-only and emits a strict plan envelope and digest only after projected documentation
validation succeeds. Unresolved Markdown, task trackers, and templates require explicit disposition and are never added
to `SUMMARY.md`. The operator saves the exact envelope outside tracked content before invoking forced apply.

Forced apply requires the saved plan and digest. It creates or reuses a digest-scoped detached worktree and temporary
Git-common artifacts, verifies the selected native Beads database and backup, rechecks the reviewed plan, and executes
only the approved operations. Successful output includes the retained migration paths and in-memory performance metrics;
these metrics are not persisted as workflow state.

A failure or interruption does not invite manual reconstruction. The retained plan, worktree, and native backup are used
by controller verification or rollback. Operators must preserve those artifacts, inspect the reported boundary, and stop
when rollback cannot prove the original state. Cleanup is explicit and occurs only after the migration has been reviewed
and integrated. A pre-existing partial migration without a matching native backup remains outside the automatic recovery
boundary.

## Architecture integration

The feature preserves the repository authority split described in the [architecture](../../architecture/index.md): Beads
owns issue state and graph transitions, Git owns source, tests, documentation, worktrees, and history, and stateless
controller code coordinates native operations. The migration plan is temporary authorized input, not a second workflow
authority.

The detached worktree protects repository files while the selected Beads database remains a shared native resource.
Every migration Beads command receives the explicit database path, including inventory, formula, backup, restore,
update, and postcondition operations. The native backup manifest and Git worktree registration provide recovery facts
without a custom state store. Closeout remains the only durable documentation reconciliation boundary before delivery.

## Design reconciliation

### Delivered as designed

The implementation delivers the accepted safety boundary: projected documentation and formula preflight precede Beads
writes; saved plans are digest- and authority-bound; migration files run in a detached worktree; native Dolt backup and
restore protect graph state; backup pointer files are restored; initialization and existing-database paths are distinct;
Git and Beads postconditions are verified; signals and ordinary exceptions enter the recovery boundary; failed artifacts
remain available; and setup does not commit, push, or delete recovery evidence automatically.

The performance design is delivered through one invocation-local inventory for normalization and postconditions, bounded
focused reads for incomplete inventory records, native multi-ID updates only for identical argument vectors, sequential
relationship and supersession writes, and non-persistent command/timing metrics. Real-Beads acceptance covers the
migration worktree, explicit database selection, backup/restore, rollback, retry, and representative grouped updates.

### Intentional differences

The accepted design separates migration application from delivery-profile diagnostics. Forced apply verifies the saved
migration and its repository/Beads postconditions; the explicitly selected `merge` or `pr` profile is supplied to the
separate setup verification or doctor boundary rather than inferred during apply. This keeps apply independent of a
future delivery choice while retaining the required explicit diagnostic mode.

### Deferred scope

Automatic recovery of a pre-existing partial migration without a matching native backup remains out of scope. The
controller does not choose semantic destinations for ambiguous documentation, integrate or push a detached worktree, or
delete retained artifacts automatically. A future native Beads transaction primitive may reduce implementation latency
only after a separate compatibility review; it is not required for this recovery boundary.

### Removed or rejected scope

No dStack database, scheduler, journal, per-operation state ledger, custom migration manifest, migration branch,
readiness cache, duplicate dependency graph, raw Dolt SQL path, or export/import rollback path was added. Parallel Beads
writes, broad cleanup, manual graph repair, and adding non-reader material to `SUMMARY.md` remain prohibited because
they would weaken authority, safety, or recovery evidence.

## Documentation

### End user and operator

Current command behavior is described in the [CLI contract](../../reference/cli.md). Failure handling, retained
artifacts, native restore, and the stop-on-uncertainty rule are described in the
[recovery guide](../../operations/recovery.md).
The `skills/dstack-beads-setup-project/SKILL.md` guide gives agents the decision-oriented preflight, apply,
verification, and recovery policy without duplicating controller choreography.

### Developer and reviewer

The [architecture guide](../../architecture/index.md) records authority ownership and the detached migration boundary.
The [development contract](../../development/index.md), [documentation guidance](../../development/documentation.md),
and [testing guide](../../development/tooling.md) establish the closeout documentation boundary, validation obligations,
real-Beads coverage, and performance evidence. The accepted design contains the detailed rationale, interfaces, security
implications, rejected alternatives, and compatibility constraints.

### Future auditor

This reconciliation, the accepted [design record](design.md), the focused setup tests, and the real-Beads scenarios form
the durable drift record. They identify the current safety invariants and known limitations without storing task,
branch, commit, or delivery bookkeeping in documentation. The [delivery guide](../../operations/delivery.md) remains the
source for the separate native integration and finalization boundary.

## Validation and limitations

The delivered candidate was validated with the configured Ruff checks, Python compilation, the full fast suite, both
real-Beads acceptance scenarios, and `bin/dstack ctl docs validate`. The real scenarios exercised native Beads 1.2.2,
Git worktrees, native backup/restore, explicit database targeting, interruption/failure recovery, retry, mdBook, and a
large-inventory grouped-write measurement. The performance assertion uses command-count reduction and a generous
wall-clock ceiling rather than a machine-specific microbenchmark.

The migration remains bounded by the pinned Beads and mdBook versions. SIGKILL, host loss, or an unavailable native
backup cannot be rolled back in-process; retained artifacts require a later explicit controller recovery. Ambiguous
legacy documentation still requires human disposition, and cleanup remains intentionally separate from migration and
delivery.
