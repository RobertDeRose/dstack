# Safe forced setup migration and recovery

## Planned intent

Make forced project setup a safe migration boundary. Deterministic validation must finish before authoritative Beads
mutation, repository changes must occur in a detached worktree, and a verified native Beads backup must make partial or
interrupted migration mechanically reversible without ad hoc repair.

## Planned acceptance

Forced setup rejects invalid projected documentation before Beads mutation, applies the exact reviewed plan in a
detached worktree with explicit database targeting, verifies a native Dolt backup before writes, restores the normalized
Beads and Git baseline after failure or interruption, reduces command amplification, and passes real-Beads, real-Git,
mdBook, bundle, clean-clone, and integrity checks without persistent duplicate state.

## Feature summary

Forced setup becomes a bounded migration transaction assembled from native Git and Beads primitives. `setup plan`
remains read-only and projects the complete post-migration repository into scratch for validation. The operator saves
and reviews its strict plan envelope. `setup apply` validates that saved envelope and digest, creates a deterministic
detached worktree, copies the plan beneath Git's common directory, verifies a native Dolt backup when a database already
exists, then executes the saved mutation object against the detached worktree and explicitly selected database.

The plan digest is the migration identifier. The artifact directory contains the reviewed `plan.json` and the native
backup, whose own manifest is authoritative; dStack adds no second manifest or journal. Git worktree registration and
HEAD describe the migration checkout. Beads backup/restore describes the database snapshot. `setup verify`, `setup
rollback`, and explicitly authorized `setup cleanup` derive their inputs from those native facts and the reviewed plan.

## User intent

Operators need `/setup-project --force` to stop safely when legacy projects are large or malformed. They must be able to
inspect the proposed changes before mutation, trust that non-reader documentation was not silently published, recover
from timeouts or process interruption through one controller command, and review the isolated migration before deciding
whether to commit and integrate it.

Agents need an unambiguous stop rule: uncertain setup state is never reconstructed with manual `bd`, Git, or
documentation edits. The retained reviewed plan, worktree, and native backup are the only recovery inputs.

## Goals

- Validate the complete projected repository, including mdBook navigation and rendering, before the first Beads write.
- Keep source-worktree tracked content unchanged while forced setup modifies migration-owned repository files.
- Protect an existing Beads database with a verified full native Dolt backup.
- Target the intended Beads database explicitly from every setup Beads invocation after the database path is resolved.
- Execute the exact saved plan only after a fresh read-only recomputation proves it still matches current authority.
- Restore the pre-migration normalized Beads inventory and detached worktree after caught failure or explicit rollback.
- Retain recovery artifacts after success or failure until explicit cleanup authorization.
- Reduce avoidable Beads subprocess calls without parallelizing writes or weakening postconditions.
- Prove the timeout, interruption, restore, retry, documentation, and performance boundaries with real tools.

## Non-goals

- Automatically recovering any pre-existing partial migration without an applicable native backup or separate user
  authorization.
- Redesigning feature, alignment, setup-doctor, or delivery lifecycles.
- Adding a dStack database, daemon, scheduler, migration branch, transaction journal, per-operation state ledger,
  migration map, readiness cache, duplicate graph, or custom backup format.
- Persisting migration IDs, worktree paths, backups, or recovery state in Beads or tracked documentation.
- Automatically committing, integrating, pushing, deleting a worktree, or deleting a backup.
- Guessing semantic placement for ambiguous legacy Markdown.
- Treating a larger timeout as recovery or replacing native Beads backup with export/import or raw Dolt SQL.

## User-visible behavior

`setup plan --root ROOT --force` remains side-effect free. It emits one strict plan envelope, including the canonical
mutation object and digest, only after a scratch projection passes documentation policy, mdBook build, formula, Git,
filesystem, and Beads planning checks. Ambiguous Markdown, `**/tasks.md`, and `features/_template/**` are reported as
blocking disposition work; they are never suggested as `SUMMARY.md` chapters.

The operator saves the exact envelope outside tracked content and invokes:

```text
setup apply --root ROOT --force --plan-file PLAN.json --plan-digest DIGEST --delivery-mode merge|pr
```

Apply uses the digest as the migration identifier and stores the reviewed plan under
`$(git rev-parse --git-common-dir)/dstack/setup/DIGEST/plan.json`. It creates a detached worktree at a deterministic
sibling path derived from the source root and digest. For an existing Beads database it creates a native backup under
the same artifact directory, restores that backup into a disposable database, and compares normalized inventories
before any migration write. Temporary `.beads/dolt-backup*.json` pointer files are restored to their exact prior
presence and bytes after backup creation.

Apply then recomputes the read-only plan against the unchanged source and explicit database, requires exact canonical
mutation and authority equality, and executes the saved object in the detached worktree. Successful apply runs the same
verification exposed by:

```text
setup verify --root ROOT --migration-id DIGEST --delivery-mode merge|pr
```

A caught failure attempts rollback automatically. After an interruption or retained failure, the operator runs:

```text
setup rollback --root ROOT --migration-id DIGEST
```

Rollback restores an existing database from the native backup, or removes only migration-created Beads runtime data
when the reviewed plan authorized initialization from absence. It derives the original checkout boundary from native
Git ancestry, refuses a migration already integrated into the source branch, resets only the detached migration
worktree, and removes only untracked paths declared as setup-created by the plan. It verifies normalized Beads equality
and worktree cleanliness, then retains the worktree, plan, and backup for inspection.

After the operator has reviewed and integrated the migration, a separate explicit `setup cleanup --root ROOT
--migration-id DIGEST` removes only a verified clean/unregistered migration worktree and that migration's artifact
directory. Cleanup refuses dirty, registered, missing, ambiguous, or unverified state and never runs automatically.

## Requirements

### Projected repository validation

Planning must create an isolated scratch copy of the relevant current repository content, apply the planned filesystem,
formula, interaction-policy, documentation move, navigation, and reference operations there, and run the existing
strict documentation validator. That validator already detects broken local links, orphaned Markdown, invalid decision
records, invalid source configuration, and mdBook build failures.

Planning adds explicit non-reader classification before navigation generation. Any matched `**/tasks.md` or
`features/_template/**` path requires operator disposition and blocks readiness. Any other unresolved documentation move
also blocks. A blocked plan contains diagnostics but cannot be authorized for apply. Scratch creation and deletion must
not alter the repository, Git index, Beads database, or worktree registrations.

### Reviewed plan and migration identity

The complete plan envelope is supplied through `--plan-file`; shell text is not reconstructed into JSON. The existing
canonical setup mutation digest remains review authorization and becomes the migration ID. Apply validates strict schema,
root agreement, requested `--init`/`--force` mode, authority, digest, and path containment before copying the plan beneath
the Git common directory.

Apply performs one fresh read-only plan computation and requires exact equality with the saved canonical mutation object.
The recomputation is a precondition check only. Execution consumes the saved object and does not rediscover broader
normalization. Changed repository, database, runtime, controller, or documentation authority requires a new review.

No custom `manifest.json` is introduced. The reviewed plan supplies intended operations and source root; native Git
worktree records supply checkout identity and detached HEAD; the native backup manifest supplies backup identity. The
artifact path is derived from the digest, so rollback requires no custom lookup state.

### Detached migration worktree

Apply requires the source worktree to be clean except the already supported local interaction-log case. It creates a
detached worktree from the source `HEAD` without a migration branch. The derived path must be absent or an exact reusable
migration worktree for the same digest; symlinks, conflicting registrations, unexpected content, and a changed detached
HEAD fail closed.

All repository file and index operations run in the migration worktree. Apply does not commit. Verification requires the
source worktree's tracked status and HEAD to remain unchanged and the migration worktree HEAD to remain at its starting
commit until the operator performs separately authorized native Git integration.

### Explicit Beads database targeting

Setup resolves the supported contained Beads runtime path before creating migration artifacts. Every subsequent native
Beads command, including inventory, update, delete, backup, restore, formula validation, and postcondition reads, receives
`--db` with that exact path. A command that cannot accept explicit selection must be replaced by an equivalent supported
call or the migration must stop; worktree auto-discovery is forbidden.

For `--init`, the plan's absence precondition identifies the contained target runtime path. Native initialization creates
the runtime database at that explicit source-repository path while setup-owned stable `.beads` files are materialized in
the migration worktree. Rollback removes only runtime content proven to have been created by that migration.

### Native backup and restore

An existing database must be backed up with pinned Beads native `backup init` and `backup sync` before any authoritative
write. Backup destinations are private, contained under the migration artifact directory, and passed as structured
arguments. Apply preserves any pre-existing backup-pointer files byte-for-byte and removes migration-created pointer
files after sync.

Backup verification requires a native restore into a disposable initialized database followed by normalized inventory
comparison with the live pre-migration database. Existence of a backup manifest alone is insufficient. The disposable
restore is read-only evidence and is deleted after comparison. Backup or comparison failure blocks apply.

Normalized comparison covers issue IDs, titles, descriptions, acceptance, types, priorities, statuses, assignees,
parents, labels, metadata, dependency direction/type/endpoints, supersession, gates, and templates while excluding native
timestamps, internal storage hashes, ordering, and other nonsemantic database history.

### Apply, verify, rollback, and cleanup

Apply snapshots only setup-owned filesystem bytes and Git-index entries needed for caught-exception compensation, then
executes the saved mutation object. It groups issue updates only when their complete native argument lists are identical
and the pinned CLI accepts a multi-ID update. Writes remain sequential. Exact postcondition verification uses bounded
inventory reads where they provide all required fields and focused reads only where inventory omits required state.

Verify compares the migration worktree's status and diff with the plan's allowed paths, hashes, moves, deletions,
formulas, and index operations. It rejects unexpected content or commits, then runs formula validation, strict docs and
mdBook validation, and setup doctor with the caller's required explicit delivery mode. It compares live Beads with the
verified backup baseline and permits only changes that the saved plan describes; unrelated fields and graph edges must
remain equal.

Caught `Exception`, `KeyboardInterrupt`, SIGINT, SIGTERM, and SIGHUP enter the same best-effort rollback boundary. SIGKILL
and host loss cannot be caught; retained native artifacts make explicit rollback possible. Rollback never infers or
repairs forward. It restores the backup atomically through Beads, derives the original checkout through native linear
ancestry, refuses rollback when the source already contains the migration result, resets only the migration worktree,
removes only plan-declared creations, verifies the baseline, and reports recovery required if any proof fails.

Cleanup requires explicit invocation after integration. It verifies the source contains the committed migration
worktree result, database recovery is not pending, the worktree is clean, and Git registration/path facts are
unambiguous. It uses native `git worktree remove` and removes only the digest-scoped artifact directory after successful
unregister verification.

### Performance and observability

Apply reports per-phase duration and Beads command counts in its JSON result without persisting them. A representative
large legacy fixture establishes a measured regression budget during implementation. The acceptance threshold is based
on command-count reduction and a generous environment-tolerant duration ceiling, not an arbitrary microbenchmark.
Parallel Beads writes remain prohibited.

### Agent recovery policy

The setup skill and recovery guidance state that timeout, interruption, or uncertain mutation requires stopping. Agents
must preserve the plan and artifacts, run controller verify/rollback, or report the defect. Manual `bd update`, `bd
close`, label, Git, or documentation reconstruction is forbidden unless the user separately authorizes native recovery
because the controller cannot prove rollback.

## Existing patterns and reuse

- Reuse the strict canonical plan and digest in `setup.py`; extend apply to accept the reviewed bytes instead of adding a
  second plan format.
- Reuse `validate_docs`, which already performs orphan/link/decision checks and an actual mdBook build, against a scratch
  projection rather than building another documentation validator.
- Reuse setup's path-containment, symlink rejection, file hashing, atomic replacement, index snapshots, formula
  validation, and exact postcondition helpers.
- Reuse native `git worktree add --detach`, `git worktree list --porcelain`, `git worktree remove`, status, reset, and diff
  rather than implementing checkout state.
- Reuse pinned Beads native backup/restore and explicit `--db`; do not inspect or copy live Dolt files.
- Reuse one invocation-local Beads inventory and parent/relationship indexes. Extend `BeadsClient` narrowly so setup can
  attach an explicit database argument without changing unrelated workflow clients.
- Reuse retained-worktree failure reporting conventions from delivery recovery where applicable.

## Proposed design

The minimum implementation has four cohesive mechanics:

1. **Project:** produce a temporary projected repository, apply the canonical planned file operations, classify
   non-reader/unresolved docs, and call existing validators.
2. **Prepare:** validate the saved plan, derive the digest-scoped artifact/worktree paths, create the detached worktree,
   resolve the explicit database, create/verify the native backup, and recheck exact plan equality.
3. **Execute and verify:** apply the saved canonical object with sequential grouped writes, then compare planned Git and
   Beads deltas and run existing validators/doctor.
4. **Rollback and cleanup:** restore from native authority and verify, retaining artifacts until an explicit safe cleanup.

These may remain private functions in `setup.py` unless focused tests prove a small pure comparison or path helper merits
extraction. No interface hierarchy, plugin system, generic transaction framework, or reusable migration engine is
needed.

## Architecture consistency

The design follows [core principles](../../development/index.md): Beads owns issue state, Git owns repository content and
worktrees, and deterministic controller code owns orchestration. The temporary reviewed plan identifies user-authorized
input; it does not calculate readiness or become durable product state. The native backup is Beads recovery data, and
Git's own worktree records are checkout state.

The design refines the setup boundary documented in [architecture](../../architecture/index.md) without weakening the
prohibition on a dStack database or ledger. The digest-scoped plan copy is temporary recovery input beneath Git's common
directory, not tracked documentation or a writable authority. Removing a redundant custom manifest ensures all recovery
facts remain derivable from the reviewed plan and native Git/Beads artifacts.

## Interfaces and data flow

```text
setup plan (read-only)
  -> discover canonical mutation
  -> project operations into scratch
  -> validate docs/mdBook/formulas/preconditions
  -> emit strict envelope + digest

saved reviewed envelope
  -> setup apply validates file/digest/root/mode
  -> derive artifact directory and detached worktree
  -> resolve and pin explicit database path
  -> native backup sync
  -> disposable native restore + normalized baseline comparison
  -> fresh read-only plan equality check
  -> execute saved mutation in detached worktree against explicit database
  -> verify planned Git delta + allowed Beads delta + docs/formulas/doctor
  -> retain worktree, plan, and backup

failure/interruption
  -> setup rollback loads digest-scoped reviewed plan
  -> native backup restore or remove proven newly initialized database
  -> reset detached worktree and remove plan-declared creations
  -> compare normalized baseline and worktree state
  -> retain artifacts; report verified recovery or recovery required
```

Inputs crossing trust boundaries—plan JSON, repository files, Git metadata, Beads output, backup paths, and native command
results—are strictly parsed, path-contained, and passed as structured subprocess arguments. No shell evaluation is used.

## Failure behavior

Planning failure is mutation-free and reports every deterministic blocker practical in one pass. Apply fails before
Beads mutation for invalid saved bytes, digest/root/mode mismatch, dirty source, worktree collision, unsupported database
mode, backup/pointer failure, failed disposable restore, baseline mismatch, plan recomputation drift, or invalid projected
documentation.

After mutation begins, caught failures attempt native database restore first, then setup-owned worktree/index cleanup,
then normalized verification. The result distinguishes `rollback_verified`, `recovery_required`, retained worktree,
retained artifact directory, and the primary error. Cleanup errors never hide the primary failure.

An uncatchable interruption leaves the digest-scoped plan, native backup, and registered detached worktree. Explicit
rollback validates all three before mutation. Missing, mismatched, ambiguous, or corrupt artifacts fail closed; the
controller does not guess. A failed restore never triggers a forward retry.

## Security implications

The backup can contain private issue descriptions, comments, metadata, and operational history. Artifact directories
must be created with owner-only permissions, never printed with secret content, never committed, and retained only until
explicit cleanup. Diagnostics report paths and bounded differences, not full sensitive records unless needed to identify
an invariant failure.

Plan and artifact paths must reject traversal, symlinks, path replacement, cross-repository Git common directories, and
worktree registration races. Database paths must be contained in the selected repository's supported `.beads` runtime
location. Commands use argument arrays; migration IDs are validated SHA-256 digests. Backup restore must target only the
reviewed database and must not overwrite another repository.

Signal handling must avoid two concurrent rollback attempts. Native locks remain authoritative; lock contention fails
closed rather than bypassing Beads or Git protections.

## Compatibility and migration implications

The feature preserves pinned Beads 1.2.2, mdBook 0.5.3, current formulas, setup plan schema semantics, and explicit
`--init`/`--force` authorization. `setup plan` and `setup doctor` remain compatible. Forced `setup apply` gains required
`--plan-file` input and runs through the migration worktree; digest-only invocation is rejected with recovery guidance.
Non-forced setup may use the same safe boundary or retain its current in-place behavior only if tests prove it performs no
legacy graph migration; forced migration safety cannot be bypassed.

Existing partially migrated repositories are not automatically repaired. Recovery still requires a matching backup or
explicit user approval for native repair after this feature passes clean-clone acceptance.

No historical setup plan is upgraded in place. Missing digest-scoped artifacts require a new read-only plan unless the
repository is in uncertain state, in which case setup stops for explicit recovery.

## Validation strategy

Behavior-first fast tests are written before implementation for scratch projection, non-reader classification, strict
plan-file validation, deterministic paths, explicit database command construction, pointer-file restoration, normalized
inventory comparison, allowed Git/Beads deltas, signal-to-rollback behavior, and cleanup refusal.

Separate real-Beads acceptance scenarios prove:

- backup sync and disposable restore reproduce the normalized baseline;
- failure after each graph mutation restores the baseline;
- timeout where a mutation may have committed restores safely;
- SIGTERM/process interruption followed by rollback restores safely;
- explicit database targeting from a worktree never selects another database;
- initialization from absence removes only created runtime state;
- retry of the same reviewed plan converges without duplicate labels, relationships, templates, or navigation.

Real-Git/mdBook scenarios prove detached worktree isolation, unexpected-diff rejection, retained dirty failure evidence,
explicit cleanup safety, invalid docs blocked before the first observed Beads write, scratch mdBook rendering, and source
worktree non-mutation. A representative large inventory asserts materially fewer Beads commands and records phase timing
under a generous measured ceiling.

Release validation includes configured Ruff/static checks, Python compilation, all fast tests, each real-boundary
scenario separately, actual mdBook validation, formula/package contracts, `git diff --check`, `git fsck --full`, bundle
verification, and clean-clone execution. A timeout, skip, substitution, or incomplete recovery scenario remains blocking.

## Documentation impact

### End user and operator

- Usage and configuration: update the [CLI contract](../../reference/cli.md) with saved-plan apply, verify, rollback, and
  cleanup inputs and explain that forced setup runs in a detached worktree.
- Deployment, upgrade, and rollback: update [delivery operations](../../operations/delivery.md) only if integration of a
  detached setup result needs a stable native Git procedure; setup itself never commits or pushes.
- Operations, troubleshooting, and recovery: replace the current manual correction advice in
  [recovery](../../operations/recovery.md) with native backup rollback, retained artifacts, explicit cleanup, and the
  stop-on-uncertainty rule.

### Developer and reviewer

- Architecture and structure: update [architecture](../../architecture/index.md) to describe scratch preflight,
  digest-scoped temporary artifacts, native backup authority, and explicit database targeting.
- Interfaces, contracts, and maintenance: update [development documentation](../../development/documentation.md) and the
  [development contract](../../development/index.md) where necessary, plus the setup skill, while keeping exact shell
  choreography in controller help and tests.

### Future auditor

- Decisions and rationale: this design records why a detached worktree and native backup replace per-operation recovery
  state and why no custom manifest is needed.
- Invariants, regression evidence, and known limitations: the final reconciliation, real-Beads interruption/restore
  scenarios, real-Git isolation checks, and [recovery guide](../../operations/recovery.md) provide durable drift evidence.

## Risks and tradeoffs

- Native backup and disposable restore add latency before migration. This is accepted because forced setup is rare and
  correctness outweighs startup speed; post-backup command amplification is still reduced.
- A detached worktree isolates tracked files but not the database. Explicit `--db`, containment checks, and backup are
  mandatory rather than assuming isolation Git does not provide.
- Temporary artifacts under Git's common directory are local recovery data. Retention consumes disk and may contain
  sensitive content, but automatic deletion would destroy the evidence required after interruption.
- Normalized comparison must be complete enough to detect semantic drift without comparing timestamps or Dolt history.
  Real-Beads fixtures define this boundary and unknown fields fail closed until reviewed.
- Signal recovery is best effort; SIGKILL and host failure require later explicit rollback.
- Grouped multi-ID updates improve command count but may still be interrupted. Backup restore, not grouping, provides
  atomic recovery semantics.

## Rejected alternatives

- Per-operation before/after snapshots, a custom transaction journal, or a dStack recovery database: duplicated state
  with more failure modes than native full backup.
- A migration branch: unnecessary; a detached worktree isolates content and avoids another branch lifecycle.
- A custom migration manifest: redundant with the reviewed plan, deterministic digest path, native Git registration, and
  native backup manifest.
- `bd batch`: pinned Beads does not batch required metadata, label, template, and supersession operations.
- `bd export`/`import`: import can merge labels and is not exact database rollback.
- Raw Dolt SQL or copying live database files: unsupported storage coupling that bypasses Beads safety.
- Parallel writes or only increasing timeout: neither makes partial mutation recoverable.
- Automatic `git clean`, broad worktree prune, or forced artifact deletion: can destroy unrelated data or recovery
  evidence.
- Adding task trackers or templates to `SUMMARY.md`: exposes non-reader workflow material and violates documentation
  policy.

## Open or intentionally deferred decisions

The public shape is settled as read-only `setup plan`, saved-plan `setup apply`, read-only `setup verify`, restorative
`setup rollback`, and explicitly destructive `setup cleanup`, all scoped by root and digest-derived migration ID.
Apply and verify require the existing explicit `merge` or `pr` doctor profile; they never infer it. Exact help wording
and internal function boundaries are implementation details.

The normalized Beads field set starts with every semantic field exposed by the pinned CLI and listed in Requirements.
If real-tool evidence exposes a semantic field unavailable from inventory, use a focused native read; do not ignore it.
The large-inventory wall-clock ceiling will be derived from representative measurements, while command-count reduction
is mandatory.

Future Beads transaction support may simplify implementation only after separate compatibility review. It does not defer
this feature. No product or architecture decision remains open for implementation authorization.
