# Design — Migration artifact retirement

## Metadata

- Beads feature root: `dstack-mol-b8d`
- Feature slug: `migration-artifact-retirement`
- Design path: `docs/src/features/migration-artifact-retirement/design.md`
- Implemented record: `docs/src/features/migration-artifact-retirement/index.md`
- Base branch: `main`
- Status: reviewed

## Existing Context

`/migrate-workflow` already records durable migration authority, manifests, reports, baselines, session approvals, and
legacy-task archives. It also creates delivered-record candidates for review, but those files are staging material and
must not become a second source of migration truth.

## Feature Summary

Document and enforce the temporary lifecycle of delivered-record candidate files created by `/migrate-workflow`.

## User Intent

`migration/delivered-record-candidates/` is a local review workspace, not migration evidence that belongs in commit
history. Agents must not stage or commit those files. After migration has passed final verification, the agent may
remove the directory. The migration can be resumed in the same worktree while the files remain; if they are lost, the
agent reruns candidate drafting and review rather than recovering them from Git history.

## Goals

- Tell `/migrate-workflow` agents exactly which candidate files are transient.
- Keep candidate files out of ordinary migration commits by using explicit durable staging paths.
- Permit a successfully finalized migration to verify after the transient candidate directory is removed.
- Keep the change to one small implementation task covering the procedure, verifier behavior, and regression test.

## Non-Goals

- Do not remove or make transient the baseline, manifest, report, session-authority, resume-approval, or legacy-task
  archive artifacts. Those records explain and validate the migration.
- Do not add candidate dispositions, historical Git-blob fields, retirement journals, a compatibility command, or a new
  migration workflow.
- Do not change Beads import, semantic review, feature records, finalization transactions, or remote Git behavior.
- Do not automatically delete candidate files before final verification.
- Do not generalize cleanup to arbitrary files under `migration/`.

## Artifact Policy

| Artifact                                                | Lifecycle                                  | Commit policy                                 |
|---------------------------------------------------------|--------------------------------------------|-----------------------------------------------|
| `migration/baseline.json` and `migration/baseline.md`   | durable migration evidence                 | commit                                        |
| `migration/workflow-migration.json` and `.md`           | durable migration state and report         | commit                                        |
| `migration/session-authority.json` and resume approvals | durable authority audit                    | commit                                        |
| `migration/legacy-tasks/`                               | durable legacy intent archive              | commit                                        |
| `migration/delivered-record-candidates/`                | transient review workspace                 | never commit; remove after final verification |
| `migration/template-adoption-candidates/` and backup    | conditional temporary reconciliation state | follow their existing disposition procedure   |

Candidate files are useful for same-worktree interruption and review, but they are not the authority for resume. The
manifest, Beads state, committed checkpoints, and explicit migration authority remain the workflow evidence. A new
worktree or a missing candidate directory before finalization requires rerunning `draft-delivered-records` and semantic
review; a finalized migration intentionally permits the directory to be absent.

## Proposed Design

Keep delivered-record candidates local through review and finalization. Enforce the pre-finalization presence and digest
checks in the migration core, preserve finalized verification after intentional cleanup, and reject any attempt to
redraft a finalized migration.

## User-Facing Behavior

1. `draft-delivered-records --apply` writes candidates under `migration/delivered-record-candidates/`.
2. The agent reviews each candidate and promotes the actual implemented record. Candidate files remain available for
   review until final verification.
3. Checkpoints stage only durable migration paths and promoted records. Commands must not use `git add -A` when
   candidate files are present.
4. `finalize --apply` performs a preflight that every reviewed candidate path exists and still matches its recorded
   digest before it sets `migration_finalized`. A missing or changed candidate fails finalization and leaves the
   migration unfinished. Finalization does not delete candidate files automatically.
5. After `finalize --apply` succeeds and `verify --beads` reports completion for a manifest with
   `migration_finalized: true`, the user may explicitly authorize removal of `migration/delivered-record-candidates/`.
   The agent then removes the directory and reruns verification. A finalized manifest does not fail merely because this
   transient directory is absent.
6. If candidates disappear before finalization, verification and finalization fail. Redrafting a missing candidate
   clears its prior review metadata even when regenerated bytes have the same digest, so semantic review must run again.
   After finalization, candidate absence is intentional and does not trigger redrafting.

## Operational Considerations

Agents use explicit durable staging paths and never use `git add -A` while delivered candidates exist. Candidate cleanup
is manual: it follows successful `finalize --apply`, completed `verify --beads` with `migration_finalized: true`, and
explicit user approval. Cleanup is followed by verification; cleanup is never an automatic finalization side effect.

## Requirements

- The migration skill and reference procedure explicitly classify delivered-record candidates as transient and prohibit
  staging or committing them.
- Migration commit examples use explicit durable paths and explicitly exclude the candidate directory.
- Verification requires reviewed candidate files while `migration_finalized` is false.
- Finalization rejects a missing or changed reviewed candidate before setting `migration_finalized`.
- Redrafting after candidate loss clears review metadata and requires fresh semantic review.
- Verification permits a missing reviewed candidate path after `migration_finalized` is true, while continuing to
  validate the manifest's semantic evidence and promoted implemented record.
- Regression tests cover deletion before finalization, redrafting after deletion, and finalized verification after
  explicit candidate deletion.
- The implementation is one self-contained task and one commit.

## Architecture Consistency

This is a small correction to the existing migration artifact contract. Durable migration records remain the audit and
resume evidence. Candidate Markdown is staging material only, so it is intentionally not copied into Git history and is
recreated when needed. The verifier already distinguishes pre-finalization from finalized state; finalization now proves
candidate presence and digest before setting that flag, and post-finalization verification permits intentional absence.
Redrafting treats a missing prior candidate as a loss of review state, even when regenerated bytes are identical.

No new authority, state machine, journal, command, Beads schema, or Git-history lookup is introduced.

## Dependencies and Parallelism

The single implementation task depends on this reviewed specification and owns the migration runtime, assigned
reader-facing documentation, tests, and one commit. No parallel implementation task, new command, or external service is
required. Close-out remains responsible for the delivered record and roadmap/navigation reconciliation.

## Documentation Impact

| Documentation concern          | Exact page                                                 | Change                                                                                                                | Owner              |
|--------------------------------|------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|--------------------|
| Migration procedure            | `skills/migrate-workflow/SKILL.md`                         | Mark delivered candidates transient, use explicit durable staging paths, and document post-verification deletion.     | `dstack-mol-u15.1` |
| Migration reference            | `skills/migrate-workflow/references/MIGRATION.md`          | Record artifact lifecycles, resume limits, and candidate deletion procedure.                                          | `dstack-mol-u15.1` |
| Operations                     | `docs/src/operations/index.md`                             | Clarify transient candidate material, explicit deletion authority, finalization boundary, and recovery.               | `dstack-mol-u15.1` |
| Migration reference            | `docs/src/reference/index.md`                              | Distinguish delivered-record candidates from template candidates and document finalization, deletion, and redrafting. | `dstack-mol-u15.1` |
| Verification tests             | `tests/test_migrate_legacy_workflow.py`                    | Cover missing candidates before finalization, redrafting after loss, and finalized verification after deletion.       | `dstack-mol-u15.1` |
| Feature design navigation      | `docs/src/SUMMARY.md`                                      | Preserve the existing feature-design entry.                                                                           | `dstack-mol-u15.1` |
| Roadmap reconciliation         | `docs/src/planned-features.md`                             | Update the feature from `design` to `delivered` only during close-out after delivery.                                 | `dstack-mol-42a`   |
| Implemented feature index      | `docs/src/features/index.md`                               | Add the delivered record to the implemented-feature index during close-out.                                           | `dstack-mol-42a`   |
| Implemented SUMMARY navigation | `docs/src/SUMMARY.md`                                      | Add the delivered record to the implemented-feature marker during close-out.                                          | `dstack-mol-42a`   |
| Delivered-record page          | `docs/src/features/migration-artifact-retirement/index.md` | Create the standalone delivered record during close-out.                                                              | `dstack-mol-42a`   |

## Risks and Tradeoffs

- Losing candidates before finalization loses review state and requires redrafting and fresh semantic review.
- Keeping candidates local avoids permanent staging clutter but means they cannot be recovered from migration Git
  history; durable migration evidence remains available for resume.
- A finalized manifest tolerates candidate absence only after semantic and promoted-record verification remains valid.

## Validation Strategy

- Write tests first for deletion before finalization, redrafting after candidate loss, and finalized verification after
  deletion.
- Run the focused migration tests and the existing migration regression suite.
- Run `uv run --no-project python scripts/check-docs.py`, `mise run check`, `mise run docs:check`, and the full
  repository test suite before the task commit.
- Existing unrelated baseline failures must be reported separately rather than broaden this task.

## Implementation Decomposition

One implementation task only: `dstack-mol-u15.1` updates the migration skill/reference/operations text, adjusts the
finalized verification boundary, adds the three behavior tests, and commits the complete change.

No follow-up command, compatibility, cross-slice, or historical-proof tasks are required.

## Open Questions

There are no unresolved product or safety questions. The user explicitly selected transient candidates, manual
post-verification cleanup, and one implementation task; template-adoption candidate cleanup continues to use its
existing disposition procedure.

## Planning Record

### Questions Asked and Answers

- **Question:** Should delivered-record candidate files be transient, excluded from commits, and removable after a
  successful migration? **Answer:** Yes.
- **Question:** Should this be one small task rather than a multi-stage retirement feature? **Answer:** Yes.

### Scope Reset

The earlier design proposed candidate dispositions, historical Git-blob verification, transactional retirement journals,
and a compatibility command. That boundary was rejected as unnecessarily complex. The current design supersedes it with
one procedure-and-verifier change.
