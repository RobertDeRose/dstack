# Design — Migration artifact retirement

## Metadata

- Beads feature root: `dstack-mol-b8d`
- Feature slug: `migration-artifact-retirement`
- Design path: `docs/src/features/migration-artifact-retirement/design.md`
- Implemented record: `docs/src/features/migration-artifact-retirement/index.md`
- Base branch: `main`
- Status: reviewed

## Feature Summary

Make reviewed delivered-record candidates explicitly temporary and retire them safely during `/migrate-workflow`
finalization while preserving the audit evidence needed to reconstruct and verify the migration.

## User Intent

The migration directory should not become a permanent copy of staging material. The final repository should retain
migration evidence that explains what changed, but candidate delivered records should disappear after they are promoted
to `docs/src/features/<slug>/index.md`.

The change must preserve Git history and semantic-review evidence. It must not create a second migration workflow or
silently delete unreviewed content.

## Goals

- Classify `migration/delivered-record-candidates/` as temporary reconciliation state.
- Preserve each reviewed candidate's digest, review metadata, and Git object location in the migration manifest.
- Remove reviewed candidates transactionally during finalization after the promoted record is verified.
- Provide an explicit, idempotent retirement command for migrations completed by older dstack versions.
- Keep verification useful after candidate files are removed from the working tree.
- Preserve compatibility with manifests that still contain live reviewed candidates.

## Non-Goals

- Remove the migration manifest, report, baseline, session-authority audit, or legacy task archive by default.
- Change Beads issue state, feature semantics, or reader-facing delivered records.
- Replace human semantic review with generated-record acceptance.
- Generalize cleanup to arbitrary files under `migration/`.
- Rewrite or force-push Git history.

## User-Facing Behavior

A normal migration continues to draft and review one delivered record at a time. After all completed features are
reviewed, the operator creates an ordinary verified checkpoint containing the reviewed candidate bytes, promoted
implemented-feature records, and updated migration manifest/report. `finalize --apply` runs only from that clean,
authorized worktree with the checkpoint reachable in Git. It preflights every candidate, stages the temporary candidate
removals through the journal, and leaves the retired manifest/report ready for the next ordinary verified checkpoint;
finalization never creates an implicit commit.

The final report distinguishes durable audit artifacts from retired temporary candidates. Verification reports a retired
candidate as valid when its recorded historical Git blob matches the reviewed digest and the promoted record matches its
recorded digest.

For an already-completed migration, the canonical compatibility command is
`migrate-legacy-workflow.py retire-delivered-record-candidates [--apply]`. It first performs the complete read-only
migration verification and requires the immutable session-authority contract, current authorized branch/worktree, and a
clean worktree. It does not infer authority from `migration_finalized`, reopen Beads import, mutate Beads, or publish
Git history. It refuses unreviewed candidates, changed candidate bytes, missing or ambiguous historical matches,
incomplete migration evidence, and an unavailable original migration authority.

## Requirements

### Functional Requirements

- The manifest adds `candidate_disposition: present|retired`; manifests without the field remain `present`. Retired
  entries also record the reviewed candidate digest, promoted-record digest, `historical_git_commit`,
  `historical_git_path`, and exact `historical_git_blob` object ID.
- A reviewed candidate and its promoted record must be committed through an ordinary verified checkpoint before
  `finalize --apply` may remove the working-tree candidate.
- Historical lookup is restricted to commits reachable from the immutable authorized migration history between the
  recorded base SHA and current HEAD. It walks the candidate path with Git rename history, hashes each exact blob, and
  accepts exactly one commit/path/blob match; zero or multiple matches fail closed.
- The complete-migration preflight validates the native Beads graph, exact feature/design/task/archive inventory,
  checkpoint evidence, reviewed semantic evidence, durable artifacts, strict documentation, path safety, and the
  session-authority boundary. `migration_finalized` is evidence to inspect, never authorization by itself.
- Finalization stages candidate removals through typed journal operations and rolls them back if strict documentation
  validation or any preflight fails. The journal records operation kind, expected digest, manifest/report pre-state, and
  recovery state for both task archival and candidate retirement.
- Retirement is idempotent. Repeating it after successful cleanup changes no candidate content and produces stable
  manifest/report evidence.
- `verify` accepts legacy live candidates and new retired candidates. It rejects missing or changed historical blobs,
  changed promoted records, unreviewed candidates, unexpected candidate files, and incomplete retired-state evidence.
- Rescans preserve retired entries, and `draft-delivered-records` refuses finalized manifests or retired entries. No
  implicit unretire transition exists; reopening requires a new explicit migration boundary and review.
- The cleanup command does not mutate Beads or remote Git state and does not support an inferred post-merge or deleted-
  branch authority.

### Quality Requirements

- Candidate content is never lost without a matching reachable Git object and an explicit fail-closed error.
- The reviewed-record checkpoint and finalization checkpoint are ordinary verified commits; neither workflow step
  bypasses hooks or creates an implicit commit.
- Interrupted mixed cleanup leaves a recoverable typed journal and never guesses whether a task archive or candidate
  deletion completed.
- The implementation uses the existing migration authority, path-safety, strict-documentation, ordinary-commit, and
  report-generation patterns.
- Repeated finalization and retirement are byte-stable when semantic inputs are unchanged.
- Error messages name the candidate slug, expected disposition, digest or Git object, authority failure, and recovery
  command.

### Compatibility and Migration Requirements

- Existing completed manifests with live candidates continue to verify until the explicit retirement command is run.
- Existing manifests without candidate disposition fields remain readable as `present` and are not silently rewritten as
  retired.
- The retirement command supports the current Conduit-shaped manifest, including candidates whose content exists in an
  earlier reachable migration checkpoint commit; missing, shallow, rewritten, or ambiguous history fails closed.
- The command requires the original immutable session authority and does not support an inferred authority after a
  migration branch or worktree is merged or deleted.
- No candidate cleanup is performed for unreviewed or partially reconciled migrations, incomplete Beads state, or a
  manifest whose retired evidence is incomplete.

## Existing Context

`skills/migrate-workflow/scripts/migration_core.py` drafts and reviews delivered-record candidates, while
`migration_verification.py` currently requires reviewed candidate files to remain in the working tree. The target
implemented records live under `docs/src/features/<slug>/index.md`; candidate files are staging copies containing
historical summaries and provenance.

The completed `migration-safety-and-clarity` feature already defines candidate directories as temporary and requires
durable manifests, reports, baselines, and legacy-task archives. This feature closes the implementation gap for reviewed
delivered-record candidates without changing that artifact policy.

The workflow already has journaled finalization for legacy task archival, strict post-archival documentation checks,
path validation, and digest sealing. The design reuses those boundaries rather than adding a separate cleanup system,
extending the journal with typed candidate operations and the existing immutable session-authority contract.

## Proposed Design

Extend each reviewed delivered-record manifest entry with a monotonic candidate lifecycle state. The existing
`evidence_digest` and candidate path remain the review identity. Retired entries add `historical_git_commit`,
`historical_git_path`, and `historical_git_blob`; the latter is checked against the exact candidate bytes and
`evidence_digest`.

Before finalization, the normal workflow stages and commits the candidate files, promoted records, manifest, and report
through the repository's ordinary verified checkpoint. The checkpoint is the only source from which retirement may prove
historical reachability. `finalize --apply` then requires a clean worktree and exact session authority, preflights the
complete migration, and records typed `candidate-retirement` operations beside any `task-archive` operations. Each
operation stores source/staging/destination, expected digest, manifest/report pre-state, and rollback state. Strict
documentation validation runs against the staged result; failures restore both task and candidate operations and the
pre-finalization manifest.

The compatibility command uses the same preflight and journal machinery, requires `migration_finalized: true` only as
one input to complete-state validation, and requires the original authorized branch/worktree. It does not support merged
or deleted migration authorities. Its dry-run reports each candidate disposition, exact historical commit/path/blob
match, complete-state evidence, and planned deletion before `--apply` is accepted.

For legacy entries without historical fields, the command enumerates the authorized ancestry from the recorded base SHA
to current HEAD, follows the candidate path through Git rename history, and hashes every matching blob. Exactly one
matching commit/path/blob tuple is required; zero matches, duplicate matches, shallow history, rewritten history, or
ambiguous path resolution stops without mutation. Verification resolves a retired candidate's historical blob with Git
plumbing and hashes the exact bytes. It continues to validate present candidates for older manifests, allowing
repositories to migrate incrementally without a schema rewrite or forced cleanup.

`draft-delivered-records` refuses a finalized manifest or any retired entry, while read-only rescans preserve the
retired state and historical fields. Reopening is intentionally outside this feature and requires a new explicit
migration boundary and semantic review.

## Architecture Consistency

### Existing Patterns Reused

- Beads remains live work authority; the migration manifest is resumable evidence only.
- Git commits remain the checkpoint and historical recovery authority.
- Existing journaled finalization and path-safety guards own filesystem mutation.
- Strict documentation validation runs after transitional artifacts are removed.
- Existing compact JSON plus human-readable Markdown report remains the evidence format.
- The original immutable session authority remains the boundary for compatibility cleanup; a finalized manifest never
  authorizes a new branch, worktree, or repository.

### Invariants Preserved

- Legacy text and generated candidates never establish product truth without human review.
- Reader-facing implemented records remain under `docs/src/features/<slug>/index.md`.
- No destructive cleanup occurs without a clean worktree, reviewed digest, historical recovery proof, and a recoverable
  transaction journal.
- Old manifests remain readable and are never silently treated as fully retired.
- Remote repositories and Beads databases are not mutated by candidate retirement.

### New Decisions Introduced

- Delivered-record candidates are temporary, while migration reports, manifests, baselines, authority audits, and legacy
  archives remain durable by default.
- Candidate retirement is represented explicitly in the manifest rather than inferred from a missing file.
- Git history is the retained source for an approved candidate after its working-tree copy is removed.
- A reviewed-record checkpoint is mandatory before destructive finalization; retirement never creates an implicit
  commit.
- The candidate state machine is monotonic (`present` → `retired`); drafts cannot silently resurrect retired evidence.
- Compatibility cleanup uses the existing session-authority contract and fails closed when the original authority is
  gone.

### Architecture Documentation Changes

Update the migration boundary in `docs/src/architecture/index.md` to distinguish durable migration evidence from retired
temporary delivered-record candidates and to document historical Git-blob verification.

## Operational Considerations

Operators should run the dry-run form of the retirement command first when upgrading an already-completed migration. The
command must be run from the repository authority with a clean worktree. If a candidate's historical commit is missing
because history was shallow-copied or rewritten, the command stops and reports the exact candidate and required
recovery; it does not reconstruct or discard the record.

After successful finalization or retirement, `migration/` still contains audit artifacts. The absence of
`migration/delivered-record-candidates/` is expected and is not evidence that semantic review was skipped.

## Documentation Impact

| Documentation concern      | Exact page                                                                               | Create or update        | Planned change                                                                                                                       | Owning Beads task  |
|----------------------------|------------------------------------------------------------------------------------------|-------------------------|--------------------------------------------------------------------------------------------------------------------------------------|--------------------|
| Architecture               | `docs/src/architecture/index.md`                                                         | Update                  | Document durable migration evidence, temporary delivered-record candidates, Git-blob verification, and authority.                    | `dstack-mol-u15.1` |
| Usage / Operations         | `docs/src/operations/index.md`                                                           | Update                  | Explain finalization cleanup, the canonical retirement command, complete-state preflight, dry-run output, and recovery.              | `dstack-mol-u15.2` |
| Development                | `docs/src/development/index.md`                                                          | Update                  | Update the canonical migration lifecycle, checkpoint ordering, retired state, and compatibility behavior.                            | `dstack-mol-u15.1` |
| Reference                  | `docs/src/reference/index.md`                                                            | Update                  | Document candidate disposition fields, command syntax, states, authority, history lookup, and validation contracts.                  | `dstack-mol-u15.1` |
| Skill procedure            | `skills/migrate-workflow/SKILL.md` and `skills/migrate-workflow/references/MIGRATION.md` | Update                  | Define the reviewed-record checkpoint, typed retirement journal, complete preflight, and recovery.                                   | `dstack-mol-u15.2` |
| State tests                | `tests/test_migrate_legacy_workflow.py`                                                  | Update                  | Test disposition, historical Git verification, live/retired compatibility, draft/rescan monotonicity, and test-first state behavior. | `dstack-mol-u15.1` |
| Finalization tests         | `tests/test_migrate_legacy_workflow.py`                                                  | Update                  | Test checkpoint gating, complete-state validation, typed journal rollback, command cleanup, and idempotence.                         | `dstack-mol-u15.2` |
| Cross-slice tests          | `tests/test_migrate_legacy_workflow.py`                                                  | Update                  | Test current Conduit-shaped manifests, earlier checkpoints, mixed failures, and stable report evidence.                              | `dstack-mol-u15.3` |
| Design navigation          | `docs/src/SUMMARY.md`                                                                    | Update                  | Keep design registration in the feature-design marker.                                                                               | `dstack-mol-u15.1` |
| Roadmap reconciliation     | `docs/src/planned-features.md`                                                           | Update during close-out | Reconcile planned/delivered state.                                                                                                   | `dstack-mol-42a`   |
| Implemented index          | `docs/src/features/index.md`                                                             | Update during close-out | Register the standalone implemented record.                                                                                          | `dstack-mol-42a`   |
| Implemented navigation     | `docs/src/SUMMARY.md`                                                                    | Update during close-out | Register the standalone implemented record in the implemented-feature marker.                                                        | `dstack-mol-42a`   |
| Implemented Feature Record | `docs/src/features/migration-artifact-retirement/index.md`                               | Create during close-out | Preserve delivery and audit history.                                                                                                 | `dstack-mol-42a`   |

## Validation Strategy

- Each implementation child writes its behavior tests first, observes the expected failure, then implements the smallest
  change and keeps tests, code, and assigned documentation in one commit boundary.
- State tests cover candidate disposition, live/retired verification, promoted-record digests, old manifests, exact
  historical Git matching, zero/multiple matches, shallow or rewritten history, and draft/rescan monotonicity.
- Finalization tests cover the reviewed-record checkpoint gate, complete native Beads/inventory/checkpoint preflight,
  authority failures, typed mixed journal operations, rollback, documentation failure, dirty worktrees, and no remote
  mutation.
- Cross-slice tests cover the current Conduit-shaped manifest, candidates committed in earlier checkpoints, changed and
  missing evidence, repeated dry-run/apply retirement, exact candidate inventory, and stable manifest/report bytes.
- Run the migration verifier against both old live-candidate and new retired-candidate manifests.
- Run `uv run pytest`, `uv run scripts/check-docs.py`, `mise run check`, and `mise run docs:check` before delivery.

## Implementation Decomposition

1. `dstack-mol-u15.1` adds test-first candidate disposition, historical Git-blob proof, backward-compatible
   verification, retired-state monotonicity, and state/reference/architecture/development documentation.
2. `dstack-mol-u15.2` adds test-first reviewed-checkpoint and complete-state preflight, typed journaled finalization,
   the canonical compatibility command, and operations/skill/recovery documentation.
3. `dstack-mol-u15.3` adds test-first cross-slice/current-Conduit fixtures, earlier-checkpoint compatibility, stable
   report evidence, and remaining failure-injection/idempotence coverage. It does not own final documentation
   reconciliation; that remains `dstack-mol-42a`.

## Dependencies and Parallelism

The state/verification task is the prerequisite for cleanup, and the cleanup command is the prerequisite for cross-slice
compatibility tests. Each implementation child depends on `spec-reconcile` and owns its tests before its code. State and
command documentation are assigned to their implementation owners; delivered-record, roadmap, feature-index, and
implemented-navigation reconciliation remains the close-out task. No external service or Beads schema change is
required.

## Rollout and Migration

New migrations retire candidates during finalization. Existing complete migrations remain valid with candidates present
and can opt into explicit retirement after upgrading the workflow. No automatic cleanup runs during skill installation
or project update.

## Risks and Tradeoffs

Retaining a historical Git-blob reference adds manifest fields and makes shallow or rewritten history visible as a
migration limitation. This is preferable to silently retaining redundant staging files or silently losing reviewed
content. A one-time compatibility command adds surface area, but avoids reopening completed Beads migrations. Requiring
the original session authority intentionally prevents cleanup from becoming an inferred post-merge workflow.

## Rejected Alternatives

- Keep all candidate files forever: simple, but contradicts the documented temporary-artifact contract and duplicates
  promoted records.
- Delete candidates without historical verification: smaller repositories, but unsafe and unauditable.
- Create a separate top-level workflow: unnecessary; this is a lifecycle correction within `/migrate-workflow`.
- Rely only on Git history without manifest digests: difficult to verify and easy to misattribute across candidates.

## Open Questions

None blocking implementation. The canonical cleanup command is `retire-delivered-record-candidates`; its authority,
complete-state, history-match, monotonic-state, and journal contracts are fixed by this design.

## Deferred Decisions

None.

## Planning Record

### Questions Asked and Answers

- **Question:** Should this be a new workflow? **Answer:** No. It is a follow-up feature that corrects the existing
  `/migrate-workflow` artifact lifecycle.
- **Question:** Which artifacts remain durable? **Answer:** Keep migration reports, manifests, baselines, authority
  audits, and legacy task archives by default; retire delivered-record staging candidates after review.
- **Question:** How is candidate content preserved? **Answer:** Record its digest and historical Git blob, then remove
  only the working-tree copy after verification.

### Assumptions

- Candidate content is committed in an ordinary verified checkpoint before finalization or can be located in the
  authorized repository history for a completed older migration.
- Existing journaled finalization is the correct mutation boundary for candidate removal when extended with typed
  candidate operations and manifest/report rollback state.
- A complete old migration can be cleaned without reopening Beads lifecycle state when its original session authority
  remains available; merged or deleted authorities fail closed.

### Specification Review Changes

- Added an ordinary reviewed-record checkpoint before destructive finalization and made its reachable Git history the
  only historical source for retirement.
- Defined complete-migration preflight, immutable session-authority requirements, deterministic single-match history
  lookup, and monotonic `present` → `retired` behavior.
- Extended the journal contract to typed mixed operations with manifest/report rollback state.
- Recomposed implementation ownership so state and command children write tests first, while cross-slice tests remain in
  the final child and close-out documentation owns delivered-record/navigation reconciliation.
- Corrected documentation ownership to the canonical development and reference pages and named roadmap/index/navigation
  close-out paths explicitly.

### Design Changes During Planning

- The proposal was narrowed from removing the entire `migration/` directory to retiring only temporary delivered-record
  candidates.
- Compatibility for already-completed migrations was added so cleanup does not require a new migration run.

### Source Material

- `docs/src/features/migration-safety-and-clarity/design.md`
- `docs/src/architecture/index.md`
- `docs/src/operations/index.md`
- `docs/src/development/index.md`
- `docs/src/reference/index.md`
- `skills/migrate-workflow/SKILL.md`
- `skills/migrate-workflow/references/MIGRATION.md`
- User decision in planning conversation
- Skill version evidence:

  <!-- rumdl-disable MD013 -->

  ```text
  Skill version evidence: schema=dstack.skill-version.v1 skill=plan-features installed=0.9.2 canonical=0.9.3 status=stale installed_source=/Users/DeRoseR/.agents/skills/plan-features/SKILL.md checked_at=2026-08-10T16:00:49.012745Z canonical_source=/Users/DeRoseR/workspace/personal/dstack canonical_commit=f99f38272f7681aaa25eb9a96af993157b4b2237 action=npx skills update
  ```

  <!-- rumdl-enable MD013 -->
