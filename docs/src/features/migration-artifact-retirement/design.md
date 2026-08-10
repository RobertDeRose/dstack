# Design — Migration artifact retirement

## Metadata

- Beads feature root: `dstack-mol-b8d`
- Feature slug: `migration-artifact-retirement`
- Design path: `docs/src/features/migration-artifact-retirement/design.md`
- Implemented record: `docs/src/features/migration-artifact-retirement/index.md`
- Base branch: `main`
- Status: draft

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
reviewed, `finalize --apply` verifies that each candidate was committed, that its recorded Git object still matches its
digest, and that the promoted implemented-feature record is present and unchanged. It then removes the temporary
candidate directory as part of the journaled finalization transaction.

The final report distinguishes durable audit artifacts from retired temporary candidates. Verification reports a retired
candidate as valid when its recorded historical Git blob matches the reviewed digest and the promoted record matches its
recorded digest.

For an already-completed migration, an explicit command such as
`migrate-legacy-workflow.py retire-delivered-record-candidates --apply` performs the same checks and cleanup without
reopening Beads import or semantic reconciliation. It refuses dirty worktrees, unreviewed candidates, changed candidate
bytes, missing historical blobs, and ambiguous manifest state.

## Requirements

### Functional Requirements

- The manifest adds an explicit candidate disposition. Existing manifests without the field remain interpreted as
  `present`; newly finalized candidates record `retired` plus the candidate digest, Git commit, and repository path.
- Finalization requires every completed feature's candidate to be reviewed and the candidate content to exist in Git
  history before removing the working-tree copy.
- The historical Git blob must hash to the reviewed candidate digest. The check must not trust only a commit subject,
  current path, or manifest boolean.
- Finalization stages candidate removals through the existing journal and rolls them back if strict documentation
  validation or any preflight fails.
- Retirement is idempotent. Repeating it after successful cleanup changes no candidate content and produces stable
  manifest evidence.
- `verify` accepts both legacy live candidates and new retired candidates. It rejects missing or changed historical
  blobs, changed promoted records, unreviewed candidates, and unexpected candidate files.
- The cleanup command operates only on a complete migration manifest and does not mutate Beads or remote Git state.

### Quality Requirements

- Candidate content is never lost without either a matching Git object or an explicit fail-closed error.
- Interrupted cleanup leaves a recoverable journal and never guesses whether a deletion completed.
- The implementation uses the existing migration path-safety, strict-documentation, ordinary-commit, and report
  generation patterns.
- Repeated finalization and retirement are byte-stable when semantic inputs are unchanged.
- Error messages name the candidate slug, expected disposition, digest or Git object, and recovery command.

### Compatibility and Migration Requirements

- Existing completed manifests with live candidates continue to verify until the explicit retirement command is run.
- Existing manifests without candidate disposition fields remain readable and are not silently rewritten as retired.
- The retirement command must support the current Conduit-shaped manifest, including candidates whose content already
  exists in an earlier migration checkpoint commit.
- No candidate cleanup is performed for unreviewed or partially reconciled migrations.

## Existing Context

`skills/migrate-workflow/scripts/migration_core.py` drafts and reviews delivered-record candidates, while
`migration_verification.py` currently requires reviewed candidate files to remain in the working tree. The target
implemented records live under `docs/src/features/<slug>/index.md`; candidate files are staging copies containing
historical summaries and provenance.

The completed `migration-safety-and-clarity` feature already defines candidate directories as temporary and requires
durable manifests, reports, baselines, and legacy-task archives. This feature closes the implementation gap for reviewed
delivered-record candidates without changing that artifact policy.

The workflow already has journaled finalization for legacy task archival, strict post-archival documentation checks,
path validation, and digest sealing. The design reuses those boundaries rather than adding a separate cleanup system.

## Proposed Design

Extend each reviewed delivered-record manifest entry with a candidate lifecycle state. The existing candidate digest and
path remain the review identity; new fields identify the historical Git commit and repository path used to prove that
the reviewed bytes remain recoverable after retirement.

During finalization, preflight every candidate before changing the worktree. Confirm review status, candidate bytes,
manifest digest, historical Git blob, implemented-record digest, and candidate path safety. Add candidate deletions to
the existing finalization journal. Run strict documentation validation against the staged result. On success, persist
the retired disposition and commit the manifest/report and removals through the normal verified checkpoint. On failure,
restore the candidate files and retain the pre-finalization manifest.

The compatibility command uses the same preflight and journal machinery but requires `migration_finalized: true`. It
updates only migration evidence and candidate paths; it does not reopen or alter Beads records. Its dry-run reports each
candidate's disposition, historical source, and planned deletion before `--apply` is accepted.

Verification resolves a retired candidate's historical blob with Git plumbing and hashes the exact bytes. It continues
to validate present candidates for older manifests, allowing repositories to migrate incrementally without a schema
rewrite or a forced cleanup.

## Architecture Consistency

### Existing Patterns Reused

- Beads remains live work authority; the migration manifest is resumable evidence only.
- Git commits remain the checkpoint and historical recovery authority.
- Existing journaled finalization and path-safety guards own filesystem mutation.
- Strict documentation validation runs after transitional artifacts are removed.
- Existing compact JSON plus human-readable Markdown report remains the evidence format.

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

| Documentation concern      | Exact page                                                                               | Create or update        | Planned change                                                                                         | Owning Beads task   |
|----------------------------|------------------------------------------------------------------------------------------|-------------------------|--------------------------------------------------------------------------------------------------------|---------------------|
| Architecture               | `docs/src/architecture/index.md`                                                         | Update                  | Document durable migration evidence, temporary delivered-record candidates, and Git-blob verification. | `dstack-mol-u15.1`  |
| Usage / Operations         | `docs/src/operations/index.md`                                                           | Update                  | Explain finalization cleanup, the legacy-migration retirement command, dry-run behavior, and recovery. | `dstack-mol-u15.2`  |
| Development                | `docs/src/development/feature-lifecycle.md`                                              | Update                  | Describe the migration artifact lifecycle and compatibility behavior for old manifests.                | `dstack-mol-u15.1`  |
| Reference                  | `docs/src/reference/tooling.md`                                                          | Update                  | Document candidate disposition fields, command syntax, states, and validation contracts.               | `dstack-mol-u15.1`  |
| Skill procedure            | `skills/migrate-workflow/SKILL.md` and `skills/migrate-workflow/references/MIGRATION.md` | Update                  | Make delivered-record candidates temporary and define finalization/retirement recovery.                | `dstack-mol-u15.2`  |
| Tests                      | `tests/test_migrate_legacy_workflow.py` and migration verification tests                 | Update                  | Cover historical blob verification, transactional cleanup, compatibility, and idempotence.             | `dstack-mol-u15.3`  |
| Navigation                 | `docs/src/SUMMARY.md`                                                                    | Update if required      | Register this feature design between the existing feature-design markers.                              | `dstack-mol-u15.1`  |
| Implemented Feature Record | `docs/src/features/migration-artifact-retirement/index.md`                               | Create during close-out | Preserve delivery and audit history.                                                                   | Close-out lifecycle |

## Validation Strategy

- Run focused migration tests for candidate drafting, review, finalization, and retirement.
- Add a fixture where a reviewed candidate is present in a prior Git commit and verify that retirement removes only the
  working-tree copy while historical verification passes.
- Add failure fixtures for an unreviewed candidate, a changed candidate, a missing historical blob, a changed final
  record, a dirty worktree, and a documentation-validation failure; assert no partial cleanup remains.
- Run repeated dry-run/apply retirement and assert idempotence and stable manifest/report bytes.
- Run the migration verifier against both old live-candidate and new retired-candidate manifests.
- Run `uv run pytest`, `uv run scripts/check-docs.py`, `mise run check`, and `mise run docs:check` before delivery.

## Implementation Decomposition

1. Add the candidate disposition schema, historical Git-blob proof, and backward-compatible verification.
2. Integrate candidate retirement into journaled finalization and add the explicit cleanup command for completed old
   migrations.
3. Add focused migration fixtures and failure-injection coverage, then update the skill and reader-facing contracts.

## Dependencies and Parallelism

The state/verification task is the prerequisite for cleanup. Test and documentation work depends on the finalized state
and command contract. No external service or Beads schema change is required.

## Rollout and Migration

New migrations retire candidates during finalization. Existing complete migrations remain valid with candidates present
and can opt into explicit retirement after upgrading the workflow. No automatic cleanup runs during skill installation
or project update.

## Risks and Tradeoffs

Retaining a historical Git-blob reference adds manifest fields and makes shallow or rewritten history visible as a
migration limitation. This is preferable to silently retaining redundant staging files or silently losing reviewed
content. A one-time compatibility command adds surface area, but avoids reopening completed Beads migrations.

## Rejected Alternatives

- Keep all candidate files forever: simple, but contradicts the documented temporary-artifact contract and duplicates
  promoted records.
- Delete candidates without historical verification: smaller repositories, but unsafe and unauditable.
- Create a separate top-level workflow: unnecessary; this is a lifecycle correction within `/migrate-workflow`.
- Rely only on Git history without manifest digests: difficult to verify and easy to misattribute across candidates.

## Open Questions

None blocking implementation. The cleanup command name may be finalized during implementation without changing its
contract or safety behavior.

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

- Candidate content is committed before finalization or can be located in the repository's reachable Git history.
- Existing journaled finalization is the correct mutation boundary for candidate removal.
- A complete old migration can be cleaned without reopening Beads lifecycle state.

### Design Changes During Planning

- The proposal was narrowed from removing the entire `migration/` directory to retiring only temporary delivered-record
  candidates.
- Compatibility for already-completed migrations was added so cleanup does not require a new migration run.

### Source Material

- `docs/src/features/migration-safety-and-clarity/design.md`
- `docs/src/architecture/index.md`
- `docs/src/operations/index.md`
- `docs/src/reference/tooling.md`
- `skills/migrate-workflow/SKILL.md`
- `skills/migrate-workflow/references/MIGRATION.md`
- User decision in planning conversation
- Skill version evidence:

  <!-- rumdl-disable MD013 -->

  ```text
  Skill version evidence: schema=dstack.skill-version.v1 skill=plan-features installed=0.9.2 canonical=0.9.3 status=stale installed_source=/Users/DeRoseR/.agents/skills/plan-features/SKILL.md checked_at=2026-08-10T16:00:49.012745Z canonical_source=/Users/DeRoseR/workspace/personal/dstack canonical_commit=f99f38272f7681aaa25eb9a96af993157b4b2237 action=npx skills update
  ```

  <!-- rumdl-enable MD013 -->
