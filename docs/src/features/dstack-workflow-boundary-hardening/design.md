# Feature design

## Goal

Make dStack's implementation, validation, and delivery boundaries explicit so one user command cannot silently advance
into a later lifecycle phase. Correct the design-path and documentation-policy assumptions exposed by dogfooding without
adding workflow state or duplicating Beads or Git authority.

## User-visible behavior

- `/implement-feature [feature] [task|--all]` claims and completes only the requested ready implementation work. `--all`
  repeats over the current native ready implementation tasks, then reports and stops. It never closes the implementation
  workstream, claims closeout, loads `/close-feature`, or starts delivery.
- Each implementation task follows one visible sequence: inspect and claim, implement, run focused and task-required
  checks, review and correct the candidate diff, stage and commit through `dstackctl`, verify committed evidence, then
  finish the Bead.
- A required check that fails, times out, is interrupted, misses its intended scope, unexpectedly skips required tests,
  or is replaced with weaker coverage is incomplete validation. The current task or closeout remains open, so native
  Beads blockers prevent later lifecycle work and delivery. Reports name the exact checks that ran and distinguish
  focused task checks from full/release validation.
- `/close-feature` alone closes the implementation workstream, claims closeout, runs the repository's full/release
  validation, reconciles documentation and review findings, and requests the selected delivery mode.
- Normal merge and PR finalization continue to snapshot tracked Git state and reject any Git mutation caused by Beads
  finalization. They never create a post-delivery bookkeeping commit. An explicit user-authorized rollback, reset,
  repair, history rewrite, or correction after a failed or incorrect delivery remains an ordinary Git operation outside
  dStack's delivery lifecycle.
- Every feature uses `docs/src/features/<slug>/design.md`, the mdBook feature directory. A nonconforming command path
  fails before Beads mutation.
- The documentation guard rejects reliably structured dStack bookkeeping but permits domain prose such as
  `Status: blocked` and `Status: completed`.
- Workflow guidance recommends a fresh agent session between substantial independent features after a stable boundary. A
  fresh session resumes from Beads, Git, and durable repository documentation only.

## Non-goals

- No validation ledger, lifecycle node, recovery command, agent-session state, task-planning command, scheduler,
  workflow engine, reviewer topology, or additional readiness, ownership, dependency, or approval authority.
- No controller-owned test runner, persisted successful-validation record, finite review counter, Git-SHA mapping, or
  post-delivery status commit.
- No semantic classifier for generic documentation language and no repository configuration for choosing the fixed
  mdBook design directory.
- No automatic closeout or delivery, even when every implementation task is complete.
- No change to rewrite-safe `Beads: <id>` commit footers.

## Existing patterns and reuse

- Reuse the separate implementation and close-feature skills as the user authorization boundary. Reuse native Beads
  open/blocked/closed state and the existing implementation fan-in instead of recording another validation or lifecycle
  state.
- Reuse task acceptance criteria and repository testing documentation to decide required checks. Successful routine
  checks need no Beads comment. Only validation that must remain unresolved across a session or environment gets a
  concise native Beads comment describing the missing evidence.
- Reuse `feature finish-workstream` as the explicit close-feature transition; remove the implicit workstream close from
  `finish-task` rather than adding a new command.
- Reuse the current approved-design path metadata, safe scaffold behavior, `docs_check`, Git snapshots, commit-footer
  audit, and delivery commands.
- Reuse behavior-first fast tests for controller policy and the existing real-Beads smoke boundary. No dependency or
  abstraction is needed.

## Design

### Implementation authority and sequence

The implementation skill retains the selected feature root and optional task selection. One task is the default. `--all`
repeatedly asks Beads for native ready implementation children and stops when none remain; it does not infer or advance
later lifecycle work.

`feature finish-task` validates the approved design and reachable Git evidence, then closes only the selected task. It
reports current workstream/closeout state without closing either. `feature finish-workstream` remains idempotent and is
invoked only by `/close-feature`, preserving the existing native `children-of(implementation)` fan-in.

Review occurs against the complete candidate diff before staging and commit. Material findings are corrected and the
relevant checks rerun before `dstackctl git commit`. The committed footer evidence is then inspected before
`feature finish-task`. This order keeps each task commit bounded and avoids a review-after-finish gap.

### Validation boundary

Validation completeness is an engineering decision based on the accepted specification, task acceptance criteria,
changed behavior, and stable repository instructions. The skills must treat nonzero exit, timeout, interruption,
collection failure, wrong scope, unexpected skip, or weaker substitution as a failure. They report the exact
command/scope and outcome and stop before the corresponding finish command.

Focused checks run while implementing and after corrections. Any additional check required by the task runs before task
completion. Full/release validation runs during closeout after the complete candidate is stable, unless a task's
accepted criteria require it earlier. Because incomplete work remains open, Beads' existing dependencies block
workstream completion, closeout, and `delivery_view`; no controller validation state or success attestation is
introduced. A concise Beads comment is reserved for missing validation that must survive the current session and is not
otherwise derivable.

### Design path and documentation policy

`default_design_path` always selects `docs/src/features/<slug>/design.md`. A command-supplied path must match that
convention, and scaffold paths retain repository-relative traversal and symlink-escape checks.

The documentation guard matches only structured dStack bookkeeping: Beads or gate identity fields,
candidate/review/delivery commit fields used as workflow state, branch/worktree fields, next dStack command
instructions, and transient values under the explicit `dStack Status:` or `dStack Workflow Status:` keys
(case-insensitive, with an optional Markdown bullet prefix). It removes the generic `Status: blocked|completed|...`
match. Unqualified status fields and other domain status prose remain valid, as does durable
planned/implemented/deprecated classification.

### Closeout, delivery, and recovery

`/close-feature` explicitly finishes implementation fan-in, claims closeout, reconciles the accepted design with code,
tests, and documentation, runs the required full/release checks, reviews the final candidate, and only then closes
closeout and invokes the selected delivery operation.

Normal fast-forward delivery snapshots target HEAD and tracked status, updates the target, snapshots the merged state,
closes the Beads root, and verifies that finalization changed neither HEAD nor tracked status. PR finalization applies
the same no-mutation invariant around the Beads close. Failure leaves the error visible and authorizes no automatic
repair. If the user explicitly requests recovery after a failed or incorrect delivery, standard Git commands may repair
or rewrite history as a separate operation; dStack gains no recovery state or command.

Fresh-session guidance is documentation only. It recommends a new session after stable boundaries between substantial
independent features and requires no handoff packet because all resumable truth is already in Beads, Git, and durable
repository docs.

## Failure / security / compatibility behavior

- A validation failure or incomplete scope stops before task/closeout completion; downstream native blockers remain
  intact. Routine success is not persisted as an assertion that could become stale or be forged.
- `finish-task` no longer closes the workstream. Existing callers that want closeout must use the already-public
  `finish-workstream` command through `/close-feature`.
- Missing, nonconforming, absolute, traversing, or symlink-escaping design paths fail without writing outside the
  selected worktree.
- Documentation checks avoid false positives from domain prose while retaining deterministic rejection of structured
  dStack identities and instructions.
- Delivery fails if Beads finalization mutates tracked Git state. No automatic rollback risks hiding a partially
  completed native operation; recovery needs explicit user intent.
- Subprocess commands remain argument arrays, validation output is not treated as executable input, and no secret,
  validation transcript, or commit hash is stored in new workflow state.

## Validation strategy

- Add controller tests proving `finish-task` closes only its task, leaves the workstream open, and cannot make closeout
  ready merely because the last task completed. Keep real-Beads smoke coverage for explicit workstream fan-in.
- Add contract tests for the implementation order, `--all` stop boundary, focused-versus-full validation language,
  failure/timeout/interruption/scope/ skip handling, and explicit close-feature authority.
- Add path tests for the fixed `docs/src/features/<slug>/design.md` convention, rejection of nonconforming command
  paths, and existing path-safety regressions.
- Add documentation-policy tests that accept generic blocked/completed domain statuses and reject each structured dStack
  bookkeeping form, including the two namespaced transient-status keys.
- Add merge and PR-finalization tests that inject tracked Git mutation during Beads finalization and verify failure. Add
  durable guidance checks confirming explicit recovery is permitted only through separate user-authorized Git work,
  without a recovery lifecycle.
- Run focused fast tests while changing each boundary. Once the complete candidate is stable, run Python compilation,
  the full fast suite, each required real-Beads acceptance scenario, metadata/formula checks, `git diff --check`,
  `git fsck`, bundle verification, and clean-clone checks. Required tests must execute rather than skip.

## Documentation impact

- **End user/operator:** update the workflow reference and command/skill guidance with the implementation stop boundary,
  exact validation reporting, full/release closeout checks, delivery invariant, explicit recovery boundary, and
  fresh-session recommendation.
- **Developer/reviewer:** update architecture/testing guidance where needed and retain controller and contract tests for
  command authority, design-path convention, documentation matching, and Git mutation detection.
- **Future agent/auditor:** this design, the accepted Beads criteria, durable workflow/core docs, and behavior-first
  tests establish the boundary without a handoff packet or separate agent documentation.
