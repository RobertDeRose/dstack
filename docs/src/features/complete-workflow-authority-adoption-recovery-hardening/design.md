# Complete dStack workflow authority, adoption, and recovery hardening

> **Historical record:** setup/migration behavior described below reflects the workflow at the time this feature was
> delivered. It is superseded by the current
> [compatibility and formula-audit contract](../../reference/compatibility.md): formulas are templates, historical
> graphs are not migrated, and formula-contract drift is handled by semantic audit.

## Planned intent

Close the remaining correctness gaps in project-alignment authorization, reauthorization, legacy adoption, concurrent
claiming, delivery worktree cleanup, closed-feature audit, setup review/apply, doctor profiles, documentation migration,
and abandoned PR-gate recovery without redesigning dStack's accepted lifecycle or authority model.

## Planned acceptance

Exact-plan alignment authorization and terminal-safe reauthorization fail closed; closed-world adoption preserves valid
native dependencies and executable work; atomic no-selector claiming accepts valid race winners; failed
delivery-worktree cleanup preserves recovery evidence; closed audits use one immutable delivered candidate revision;
setup applies the exact reviewed canonical mutation set; merge and PR doctor profiles enforce only their own
prerequisites; representative legacy-documentation migrations report semantic ambiguity; abandoned PR gates can be
cancelled without candidate validation; and all required fast, real-Beads, real-Git, mdBook, integrity, bundle, and
clean-clone checks pass without new persistent dStack state or duplicated authority.

## Feature summary

This feature hardens ten established controller boundaries while preserving the four-stage feature lifecycle and the
three-tier project-alignment lifecycle. The minimum new durable identities are the finalized alignment-plan and existing
approved feature-design content digests. The canonical alignment plan directly includes its audited baseline Git
revision. Setup continues to expose a reviewed plan digest covering one canonical, exact mutation set.

The implementation remains one stateless Python process. Beads continues to own work, dependencies, gates, readiness,
claims, supersession, and completion. Git continues to own repository content, immutable delivered history, worktrees,
and `Beads:` footer evidence. mdBook remains the accepted documentation surface. Beads stores no implementation,
delivery, task, evidence, or bookkeeping commit mapping; an exact Git revision may be stored only as explicit workflow
input.

## User intent

Operators and agents need retries, concurrent claims, compatibility adoption, delivery cleanup, historical audit, and
setup recovery to be safe without remembering prior session state. Human authorization must identify exact reviewed
content, an abandoned candidate must not prevent native gate recovery, and an audit of a delivered feature must describe
the feature as delivered rather than whatever the target branch contains today.

The work also needs conservative legacy documentation migration across realistic project shapes. Mechanically known
moves should converge; semantic placement must remain a visible human decision rather than a heuristic guess.

## Goals

- Bind project-alignment authorization to one canonical finalized plan before any native authorization state closes.
- Refuse feature or alignment reauthorization unless the terminal task is exactly open and unassigned before and after
  reopening earlier lifecycle stages.
- Make legacy adoption a closed-world, evidence-aware, two-pass native Beads transformation that cannot strand
  executable work.
- Let native atomic ready-claim choose no-selector implementation work under a race, then validate and recover the
  returned claim.
- Retain temporary target worktrees and structured recovery facts when Git cannot unregister them.
- Audit closed features from one immutable delivered candidate revision derived from reachable footer evidence.
- Canonicalize the complete setup mutation set before review, hashing, comparison, and application.
- Make doctor requirements explicit for merge and PR delivery profiles.
- Prove conservative documentation migration against three representative structures.
- Allow Beads-only cancellation of an abandoned PR gate without requiring a valid Git candidate.
- Preserve every previously delivered approval, readiness, evidence, cleanliness, delivery, documentation, and authority
  invariant.

## Non-goals

- Redesigning `/plan-feature`, `/review-feature-spec`, `/implement-feature`, or `/close-feature`, or the
  project-alignment review/execute/land tiers.
- Adding a database, daemon, service, scheduler, queue, packet protocol, workflow ledger, approval manifest, ready
  cache, dependency graph, ownership ledger, reviewer topology, CI/PR poller, persistent migration map, setup-plan
  store, audit cache, or Git-to-Beads commit mapping.
- Persisting implementation, delivery, task, evidence, or bookkeeping commit mappings, branches, worktree paths,
  assignees, gates, or transient lifecycle state in durable documentation or Beads. This does not exclude the exact
  project-alignment `baseline_commit` when it is immutable audit input.
- Rewriting legacy topology during normal lifecycle commands; adoption remains an explicit compatibility operation.
- Supporting squash/rebase PR delivery or direct non-fast-forward delivery.
- Guessing semantic documentation placement.
- Automatically rolling back delivered Git history, pruning unrelated worktrees, or deleting a dirty or failed-removal
  recovery worktree.
- Broadening the supported Beads or mdBook versions without separate real-tool acceptance evidence.
- Splitting controller modules for file size, introducing a generic workflow engine, or adding abstractions without a
  demonstrated shared behavior.

## User-visible behavior

### Alignment review and authorization

`alignment finish-plan` accepts a finalized strict JSON plan, validates and canonicalizes it, verifies its exact
existing Git audit baseline, writes the canonical object as the analysis task's single authoritative description, stores
and verifies a pending plan digest on the alignment root, and only then closes analysis. `alignment approve` hashes the
same canonical bytes, independently reverifies the same Git baseline, requires the matching pending digest and closed
analysis, then converges the human gate and approval milestone. It promotes the same digest to approved and clears
pending only after native convergence.

Inspection treats alignment execution as authorized only when analysis, the exact human gate, and approval are closed;
the approved digest matches the canonical analysis description; no pending digest remains; the configured Git ref still
matches the canonical audit baseline; and current correction task content, parentage, labels, priorities, and native
blockers exactly match the approved plan. Correction claim, completion, and workstream-finish paths all invoke that same
read-side predicate before mutation. Changed plan, baseline, task content, or graph fails closed. Reauthorization
resolves the target ref and reads the existing `baseline_commit` before clearing plan identity and reopening the
boundary; a mismatch is permitted only on this explicit invalidation path and never authorizes correction execution.

### Reauthorization

Feature closeout and alignment landing must be exactly `open` with no assignee before any earlier state or digest is
changed. Claimed, in-progress, deferred, closed, hooked, pinned, unknown, unsupported, or assigned terminal work rejects
reauthorization and reports whether to finish, safely release, or supersede the workflow. The terminal task is reread
after reopening and must still be open and unassigned.

### Adoption

`adopt apply` consumes one temporary strict JSON classification document rather than relying on unrelated repeated flags
as the authoritative request. The file classifies every open executable descendant and carries any durable-evidence or
explicit-risk rationale needed for completed-history decisions. It is input data, not a persisted migration map, and is
removed by the invoking agent after use. The controller recomputes descendants, validates the complete classification
and all planned native relationships before mutation, then performs a two-pass replacement and graph translation.

Existing per-category CLI flags may remain only as a compatibility adapter into the same normalized classification
model; they cannot bypass closed-world, evidence, or graph validation. If they cannot express a required classification
or evidence decision, the command directs the operator to the classification file and performs no mutation.

### Claiming, delivery recovery, audit, setup, and doctor

A no-selector implementation claim calls native atomic ready-claim directly and accepts whichever single valid scoped
task Beads returns. Explicit selection still requires an exact result. Invalid returned work is restored to open and
unassigned state before failure is reported.

Temporary delivery worktree cleanup reports whether a retained path exists, whether Git still registers it, and whether
it is dirty. Cleanup failure never hides a primary delivery failure and never triggers recursive deletion of the
retained path.

Closed-feature audit reports both the configured target ref searched and the immutable delivered candidate revision
derived from the unique reachable closeout footer. Delivery preflight requires that footer commit to equal the clean
candidate HEAD, so no post-closeout candidate commit can make the derivation stale. Documentation and filtered footer
evidence are read from that revision. The current target tip is never substituted merely because it contains the
candidate.

Setup plan output contains the exact canonical mutation object and its digest. Digest-only apply does not receive the
original bytes: it recomputes one canonical mutation object, compares that object's SHA-256 to the reviewed digest, and,
on a match, executes that same in-memory object without rediscovery. `setup doctor --delivery-mode merge` omits remote
and GitHub requirements; `--delivery-mode pr` adds them explicitly and reports the selected mode.

`delivery cancel-pr-gate` resolves the feature and its one active native `gh:pr` gate without building or validating a
candidate. Registration, replacement, direct merge, and PR finalization retain full candidate validation.

## Requirements

### Canonical alignment-plan representation

The authoritative corrective plan is the project-alignment analysis task's native Beads description. It contains exactly
one JSON object and no Markdown wrapper. Comments remain discussion/evidence and are never part of plan identity. No
second plan copy is stored in Git or dStack state.

The object has schema identifier `dstack.alignment-plan/v1` and exactly these required top-level fields:

- `schema`: the literal schema identifier;
- `baseline_commit`: the exact full Git commit ID returned by resolving the configured project-alignment target ref used
  for the audit;
- `scope`: normalized text;
- `findings`: objects with unique `title`, `evidence`, and `rationale` strings;
- `accepted_corrections`: objects with unique `title`, `description`, `acceptance`, integer `priority`, and `depends_on`
  containing other accepted correction titles;
- `rejected_corrections`: objects with unique `title` and `rationale`;
- `validation_expectations`: strings;
- `documentation_impact`: an object containing `end_user_operator`, `developer_reviewer`, and `future_auditor` string
  arrays;
- `deferred_findings`: objects with unique `title` and `rationale`; and
- `accepted_risks`: objects with unique `title` and `rationale`.

Unknown or missing fields are rejected. Collections are always present; empty collections are `[]`. Optional scalar
values, if a future schema introduces any, use JSON `null`; omission and an empty string are never treated as
equivalent. Empty required strings, duplicate titles, unknown dependency titles, dependency cycles, booleans in integer
fields, floats, and non-finite numbers are rejected. Accepted correction titles must match the unique native correction
titles and their descriptions, acceptance, priorities, and blocking relationships after normalization; generated Beads
IDs are not plan content. Alignment plan v1 allows only the fixed implementation-approval blocker plus internal
correction blockers named by correction title. External or nonblocking correction relationships are rejected at plan
finalization rather than omitted from identity.

Every string is Unicode NFC with CRLF and bare CR converted to LF. Other leading, trailing, and interior whitespace is
preserved so a material prose change changes identity. Object keys are sorted lexicographically. Semantically unordered
arrays are sorted by normalized title or normalized scalar value; each correction's `depends_on` is sorted by title. The
controller then serializes with Python JSON semantics equivalent to `ensure_ascii=False`, `sort_keys=True`, compact
separators, `allow_nan=False`, UTF-8, no BOM, and no trailing newline. SHA-256 covers exactly those bytes.

Authors, timestamps, generated IDs, statuses, assignees, gate state, comments, comment ordering, dependency response
ordering, and other transient workflow state are excluded. `dstack.pending_alignment_plan_sha256` and
`dstack.approved_alignment_plan_sha256` identify only the canonical bytes.

The Git audit baseline is legitimate workflow input, not an implementation, delivery, task, evidence, or bookkeeping
mapping. `baseline_commit` is the exact revision already used by the alignment audit and is part of the canonical plan
authorization identity. The controller uses Git's native full commit ID directly.

`finish-plan` resolves the configured alignment target ref and requires it to equal `baseline_commit` before writing and
rereading the canonical analysis description and pending identity, then claims/closes analysis. Approval repeats that
comparison before any gate or milestone mutation. The read-side authorization predicate used by every execution mutation
repeats it again and also requires an exact correction set: one native child per accepted correction title; exact
description, acceptance, priority, parent, and work label; exactly the approval blocker plus internal blockers named by
`depends_on`; and no missing or additional correction relationship. Status, assignee, and completion progress remain
native execution state and are excluded from this content/graph comparison.

An interruption before pending verification cannot close analysis. Approval resumes only matching bytes and
`baseline_commit`, promotes only after the exact gate and milestone converge, verifies approved, clears pending, and
verifies the complete authorization predicate. Fault-injection tests cover failure before and after every baseline,
description, metadata, analysis, gate, and milestone check or mutation.

### Terminal-safe reauthorization

The shared reauthorization helper validates terminal status and assignee before clearing any digest or reopening any
issue. The only accepted predicate is `status == "open"` and absent/empty assignee. No allowlist treats an unknown
native status as open. The helper also continues to reject claimed workstream children. Alignment reauthorization also
reads the canonical `baseline_commit` and resolves the configured target before mutation. Equality confirms the existing
baseline; mismatch is reported and allowed only because reauthorization clears pending and approved plan identity before
reopening analysis. After reopening approval, gate, planning, and workstream, the helper rereads terminal, requires the
same predicate, and reports observed state on failure. Feature and alignment callers use the same helper and
behavior-focused tests.

### Operationally precise adoption classifications

The strict classification document has exactly three top-level fields: `schema` with literal
`dstack.adoption-classification/v1`, `legacy_root_id` with the selected root ID for input validation only, and one
`entries` array sorted by `legacy_id`. No top-level field is optional and unknown fields are rejected. Every entry has
exactly `legacy_id`, a `classification` enum, and a nonempty `reason`, plus only the fields required by its class.
Unknown entry fields or enum values are rejected. This common identifier binds every decision to one recomputed
descendant and makes duplicate, overlap, omission, and foreign-ID checks mechanical. The `classification` enum is
exactly `completed-history`, `remaining-implementation`, `obsolete-specification-ceremony`,
`obsolete-implementation-ceremony`, `obsolete-closeout-delivery-ceremony`, `unresolved-decision`, or
`preserved-unchanged`. The root ID and other generated IDs select Beads objects but are not copied into product docs or
a persistent map.

Class-specific fields are strict:

- `completed-history` requires a nonempty `evidence` array, `evidence_assessment` (`verified` or `accepted-risk`), and
  `accepted_risk_reason` (`null` for verified and a nonempty string for accepted risk). Every evidence record has
  exactly `kind`, `reference`, and `explanation`. `kind` is `git-footer`, `source`, `test`, or `documentation`;
  `reference` is a validated Git ref for `git-footer` and a contained repository-relative POSIX path for the other
  kinds; `explanation` is always nonempty. For `git-footer`, the controller searches the exact entry `legacy_id` footer
  reachable from the named ref. Evidence is sorted by kind, reference, and explanation. Empty arrays, unknown evidence
  fields/kinds, invalid refs, absolute/escaping paths, and empty strings are rejected;
- `remaining-implementation` requires a `replacement` object containing exact title, description, acceptance, and
  integer priority;
- each obsolete-ceremony class has no additional fields because its target is the unique corresponding lifecycle step;
- `unresolved-decision` requires `strategy` (`incorporated` or `preserve-blocker`). `specification_section` is required
  only for incorporated work and is a canonical repository-relative design path plus exact Markdown heading fragment,
  such as `docs/src/features/example/design.md#requirements`; the path must equal the new feature's canonical design and
  the heading must exist with substantive resolving content. `blocking_target` is required only for preserved blockers
  and names one stable lifecycle step label; and
- `preserved-unchanged` requires `strategy` (`reparent`, `recreate`, or `keep-legacy-root`), `surviving_parent` for
  reparent, or an exact `replacement` object for recreation. Fields not applicable to the selected strategy are JSON
  `null`, never omitted or silently treated as empty.
- **Completed durable history:** The old task is closed with a concrete adoption reason and remains native history; no
  replacement implementation task is created. Each entry carries evidence records. Reachable commits with the exact
  legacy `Beads:` footer are mechanically verified. Source, tests, or durable documentation evidence names
  repository-relative paths and an explanation and is checked for current existence. If evidence does not conclusively
  establish completion, the entry also requires a user-authorized accepted-risk reason; the adoption skill must obtain
  explicit authorization, and the controller persists that irreducible reason as a concise native comment before
  closure. Without verified evidence or explicit accepted risk, apply stops before mutation and the task must be
  unresolved or preserved.
- **Remaining implementation work:** The first pass creates or reuses one equivalent task under the new implementation
  workstream with the required work label and approval blocker. The second pass reconstructs valid internal blockers,
  outgoing compatible external blockers, supported nonblocking context, and ordering. Before supersession it also
  redirects every compatible incoming external blocking edge so each outside dependent blocks on the replacement,
  verifies the new edge, removes the old edge, and rereads the outside dependent. If an incoming blocker cannot be
  translated without changing semantics, apply fails closed before supersession. Only after both relationship directions
  and readiness-preserving postconditions verify is the old task superseded.
- **Obsolete specification ceremony:** The old item is superseded only by the new specification step after its
  classification is validated; lifecycle-only dependencies are not copied.
- **Obsolete implementation ceremony:** The old item is superseded only by the new implementation workstream after
  validation; stale coordinator or reviewer topology is not copied.
- **Obsolete closeout/delivery ceremony:** The old item is superseded only by the new closeout step after validation;
  old delivery state and Git mappings are not copied.
- **Unresolved product or architecture decision:** Apply stops unless the entry explicitly selects one of two safe
  outcomes. On the initial `incorporated` pass, the old decision remains open/reachable, blocks the new specification
  through a supported native relation, and keeps the legacy root unsuperseded. Specification review resolves it at the
  canonical `specification_section` and obtains normal design authorization. A later idempotent adoption retry verifies
  that exact section in the committed approved design and only then supersedes the old decision by the new specification
  step and permits root supersession. An interruption before supersession leaves the old decision reachable, and retry
  repeats verification. `preserve-blocker` keeps explicit native decision work reachable and blocking the named new
  authorization step through a supported relationship. If safe reachability, type-compatible blocking, incorporation,
  approval, or supersession cannot be verified, adoption stops and the legacy root remains unsuperseded. An unresolved
  decision is never converted to ordinary implementation work or obsolete ceremony.
- **Intentionally preserved unchanged executable work:** The classification selects and validates one supported
  strategy: native reparent under an appropriate surviving open container; equivalent recreation under the new
  implementation workstream followed by supersession; or retention beneath the unsuperseded legacy root. The result must
  remain reachable, correctly parented, open when appropriate, and visible to native readiness. Superseding or closing a
  container that would strand preserved executable descendants is forbidden.

Completed non-executable historical records and already closed descendants are inventoried for graph validation but need
no open-work classification. Every open executable descendant must occur exactly once. Before mutation the controller
also inventories both directions of the native graph: every outgoing relationship from the legacy root/descendants to an
external issue, and every incoming relationship from an external issue to the root/descendants. It classifies each as
preserved, redirected, or lifecycle-only removal. Unknown direction, relation, issue type, or semantic compatibility
fails planning. The root itself, foreign classification IDs, duplicates, overlaps, missing entries, unsupported issue
types, invalid reused replacements, and incompatible dependency translations fail before mutation.

The controller computes the complete transformation plan first, including all replacement content, outgoing blockers,
incoming dependents, relationship order, and whether the legacy root may be superseded. Pass one creates/reuses
replacements without superseding old work. Pass two adds and verifies replacement relationships before removing old
edges, then rereads every affected internal and external issue to prove no unrelated dependent became ready prematurely.
Only after parent, label, approval, outgoing/incoming blocker, context, ordering, and readiness postconditions verify
are old items closed/superseded and, when safe, the root superseded. Retries reconstruct intent from native
supersession, parentage, labels, content, and relationships; no map is persisted.

### Native atomic implementation claiming

With no selector, `claim_ready_work` performs one native scoped ready-and-claim call and requires exactly one result. It
validates direct parent and work label after the claim. A valid task returned after another actor won a different task
is accepted. With an explicit selector, the requested issue is validated for parent/label/status and the atomically
claimed singleton must have the same ID. Any newly claimed mismatch is passed to the existing release helper; failure to
prove open and unassigned reports ownership uncertainty.

### Delivery worktree lifecycle

When no target worktree exists, the controller creates a parent with `tempfile.mkdtemp`, creates the target path beneath
it, and registers the Git worktree. It owns cleanup explicitly. Successful `git worktree remove` is followed by a
`git worktree list --porcelain` verification that the path/branch registration is absent; only then may the empty parent
be removed.

On removal failure, the controller queries registration and full status including untracked files without mutating
either, retains the path and parent, and emits or attaches stable facts: retained path, path existence, registered
state, dirty state or `unknown`, cleanup error, and recovery guidance. An unexpected dirty worktree is never
force-deleted. If body execution already failed, that exception remains primary and cleanup facts are attached as
secondary detail. A cleanup-only failure raises a structured dStack error with the same facts.

### Immutable delivered-revision audit

The configured target branch/ref is only the search boundary. For a closed feature the immutable delivered candidate
revision is derived as follows:

1. Validate the configured target ref and scan commits reachable from it for the exact feature closeout `Beads:` footer.
2. Require exactly one reachable commit carrying that closeout footer. That commit is the candidate revision. Delivery
   preflight for direct merge, PR registration/replacement, and PR finalization requires the same unique footer commit
   to equal the clean candidate HEAD; any commit after closeout is rejected before delivery authority changes or Git
   mutation.
3. Require every expected specification and implementation footer, except explicitly recorded no-repository-change work,
   to be reachable from that candidate revision. Evidence reachable only later on the target is not feature delivery
   evidence.
4. Read design, reconciliation, linked architecture/operations/reference records, and all other audit documentation from
   that exact candidate revision. A small public Markdown-value parser replaces the audit module's private import.
5. Report the configured search ref, derived immutable revision, derivation rule, original feature branch/worktree
   presence, documentation source, evidence source, missing footers/records, and reconciliation status.

Direct delivery remains fast-forward-only, so the candidate revision is the historical target tip at delivery even after
the target advances. Supported PR delivery may fast-forward or create a merge commit only when the unchanged candidate
revision is an ancestor of the remote target; audit still uses the candidate revision, not the merge commit or current
target tip. Squash/rebase PR shapes are unsupported because the candidate is not an ancestor and PR finalization already
rejects them. If zero or multiple reachable closeout-footer commits exist, required evidence is not reachable from the
candidate, history is nonlinear in a way that defeats the rule, or the target ref is unavailable, audit reports the
limitation and fails revision consistency. It never falls back to a caller checkout, feature branch, uncommitted file,
or moving target tip.

The derived commit may appear in read-only audit output because Git owns audit history. It is never written to Beads or
dStack state.

### Canonical setup mutation plan

The reviewed identity covers a strict object with schema `dstack.setup-plan/v2` and exactly these complete mutation
arrays: `initialization`, `beads_issues`, `dependencies`, `supersessions`, `filesystem`, `git_index`, `formulas`, and
`navigation_references`. Every array is present even when empty. Presentation fields such as absolute repository root,
diagnostic ordering, unchanged formula status, human-readable health, and timestamps are excluded from the digest.
Preconditions are checked separately and cannot authorize extra mutations.

Record schemas and action enums are fixed for v2:

- `initialization`: zero or one record with `action` literal `initialize-beads`, `target` literal `.beads`,
  `precondition` literal `absent`, and `options` exactly `{skip_agents: true, skip_hooks: true, non_interactive: true}`.
  The record is present only when the user supplied `--init` and Beads is absent; absent Beads without reviewed
  initialization blocks the plan, while existing Beads requires an empty array;
- `beads_issues`: `issue_id`, `set_metadata` object, `unset_metadata`, `add_labels`, and `remove_labels`; metadata
  values are strings or JSON `null` as explicitly reviewed, and collections are never omitted;
- `dependencies`: `action` (`add` or `remove`), `source_id`, `destination_id`, and `relationship_type` using one
  supported native Beads relation;
- `supersessions`: `source_id` and `destination_id` (supersession is always an add operation; removal is unsupported by
  setup v2);
- `filesystem`: `action` (`create`, `update`, `move`, or `delete`), nullable `source`, nullable `destination`, nullable
  expected source/destination SHA-256, `content_source` (`package`, `existing-source`, or `generated`), nullable
  generated UTF-8 content, `content_preservation` (`byte-for-byte`, `generated`, or `not-applicable`), and
  `conflict_policy` (`fail-if-exists`, `require-identical`, `replace-reviewed`, or `not-applicable`);
- `git_index`: repository-relative `path` and the only setup-v2 action, `remove-cached`;
- `formulas`: `name`, `action` (`create` or `update`), repository-relative `source` and `destination`, exact
  `source_sha256`, and `conflict_policy` (`fail-if-different` or `replace-reviewed`); unchanged formulas are display
  facts, not mutations; and
- `navigation_references`: `action` (`add-navigation`, `rewrite-link`, or `rewrite-include`), `affected_path`, nullable
  `old_target`, `new_target`, and exact `expected_before_sha256` and `expected_after_sha256`.

Paths use repository-relative POSIX form, are normalized to `/`, and may not be absolute or contain `..`. Nullable
fields are explicitly JSON `null`. Unknown fields, action values, relation types, content sources, preservation
policies, or conflict policies are rejected. Together the source/destination, expected hashes, generated content where
applicable, and before/after navigation hashes bind the exact reviewed bytes and conflict behavior rather than only
naming a file.

Before serialization the controller:

- sorts initialization by target and action (although v2 permits at most one);
- sorts issues by stable ID and metadata keys lexicographically;
- sorts labels lexicographically;
- sorts dependencies by source, destination, and relationship type;
- sorts supersession by source and destination;
- sorts filesystem operations by source, destination, and operation;
- sorts Git-index operations by path and action;
- sorts formula operations by name, source, destination, and action;
- sorts navigation/reference edits by affected path, target, and operation;
- normalizes strings to Unicode NFC and LF line endings;
- represents every collection as an array, every object field explicitly, and optional scalar absence as JSON `null`;
  and
- rejects unknown fields, floats, non-finite values, absolute/escaping paths, and contradictory operations.

It then uses the same compact sorted-key UTF-8 JSON serialization defined for alignment plans, without BOM or trailing
newline, and hashes exactly those bytes. Equivalent semantic sets therefore have identical bytes regardless of Beads,
filesystem, dictionary, dependency, or platform ordering. Every changed metadata value, label, relationship,
supersession, source/destination, content expectation, navigation/reference edit, or conflict policy changes identity.

Apply receives only the reviewed SHA-256, not the original plan bytes. It recomputes and canonicalizes one complete
mutation object from current authorities, hashes those bytes, and compares that digest with the reviewed digest. On a
match it executes that same in-memory object, including Beads initialization only when the reviewed `initialization`
record is present. It cannot and does not claim a literal byte comparison with unavailable original bytes, and it does
not invoke broad normalization to rediscover a second plan. Safety rereads may detect drift and stop; they may not add
operations. Postconditions verify every operation. No plan database or journal is created.

### Delivery-mode doctor and documentation migration

`setup doctor` requires `--delivery-mode merge|pr`. Merge mode validates Git, exact Beads compatibility and native
capabilities, formula byte identity and behavior, mdBook, repository/configuration validity, interaction policy,
reconciliations, runtime paths, and local branch/worktree support. Remote and GitHub checks are reported as not
applicable to the selected mode rather than failures. PR mode adds usable target remote, GitHub repository
compatibility, authenticated `gh`, and native PR-gate capability. Every internal Python caller, CLI dispatcher,
skill/example invocation, and test passes an explicit mode; no compatibility default or remote-based inference remains.
Doctor behavior is independent of documentation-migration fixture readiness.

Three compact fixture trees cover a feature-heavy distributed service, an embedded/system platform, and a modular
application. Each proves known source moves, byte preservation, non-overwrite conflict behavior, mechanically known
link/navigation rewrites, exact unresolved Markdown paths, actionable manual navigation/link instructions, blocked
completion while ambiguity remains, and convergence after manual correction. Project-specific sections stay intact and
fixture content remains generic.

### Beads-only PR-gate cancellation

Cancellation resolves a current feature root directly from Beads, snapshots Git HEAD and full status for a no-mutation
postcondition, requires exactly one active associated gate of native type `gh:pr` and the expected blocking/waiter
relation, requires a nonempty reason, performs existing resolve/remove-blocker/relate mechanics, rereads the graph, and
verifies Git is unchanged. Missing candidate branch/worktree, invalid candidate docs, or absent footer evidence does not
enter this path. Full candidate validation remains mandatory for registration, replacement, merge, and finalization.

## Existing patterns and reuse

- Feature approval already implements pending/promoted content identity, strict committed design validation, convergent
  native closure, and digest clearing on reauthorization. Alignment reuses this transition shape with canonical native
  plan bytes rather than creating another protocol.
- `release_claim` already restores and verifies open/unassigned state. The claim fix changes selection order and reuses
  that helper.
- `descendants`, native dependency records, supersession helpers, parent/label validation, and existing external-blocker
  preservation provide adoption primitives. The new code plans the whole transformation before calling them.
- `commit_footer_ids`, Git ref validation, ancestry checks, and the one-way footer model already reconstruct reachable
  evidence. The audit narrows the revision before parsing records.
- `legacy_documentation_plan` already refuses semantic guessing and reports unresolved Markdown. Representative fixtures
  extend evidence rather than add a migration heuristic.
- Setup already emits a SHA-256 plan identity and uses atomic file replacement. The work makes its mutation content
  complete and canonical.
- PR-gate cancellation already has native gate resolution and graph verification; only the unnecessary
  delivery-candidate preflight is removed.
- Python standard-library JSON, Unicode normalization, hashing, temporary paths, and Git commands are sufficient. No new
  dependency is needed.

## Proposed design

Implement the behavior in ten bounded outcomes:

1. Canonical alignment-plan and exact Git audit-baseline identity, exact correction content/graph authorization, and
   terminal-safe feature/alignment reauthorization.
2. Closed-world adoption classification, durable-evidence validation, complete descendant/relationship inventory, and
   deterministic transformation planning.
3. Native adoption replacement creation, outgoing/incoming relationship translation, supersession, and interruption-safe
   retry; this depends on outcome 2.
4. Race-correct native atomic implementation claiming.
5. Manually managed temporary delivery worktrees with retained recovery evidence.
6. Immutable delivered-candidate audit and a public pure Markdown parser.
7. Conservative legacy-documentation migration evidence from representative fixture projects.
8. Canonical exact setup planning and application; this consumes the mechanically known migration behavior proven by
   outcome 7.
9. Explicit merge/PR doctor profiles and migration of every internal caller, with no dependency on outcome 7.
10. Beads-only abandoned PR-gate cancellation.

Each outcome includes its behavior-first fast tests and directly affected durable operator/developer documentation.
Real-tool scenarios are added to the existing separate acceptance boundaries rather than creating a new test framework.
Broad release validation remains closeout work, not an implementation coordinator task.

## Architecture consistency

The design follows [dStack architecture](../../architecture/index.md), [core principles](../../development/index.md),
and the accepted [authority decision](../../decisions/0001-authority-ownership.md). Canonical alignment JSON is stored
once in native Beads because Beads owns the corrective plan and authorization boundary. Its plan digest identifies
reviewed content but does not duplicate the plan. The plan's exact `baseline_commit` is legitimate product-independent
workflow input, not an implementation, delivery, task, evidence, or bookkeeping mapping. Canonical setup JSON is emitted
for review; only its reviewed SHA-256 is supplied to the later stateless invocation, and neither is retained as dStack
state. Existing contract rationale is specifically about rewrite-sensitive work/evidence mappings and remapping after
rebases or amends; no documented security or native-tool constraint requires an absolute ban on immutable revisions that
are themselves workflow input.

The immutable audit revision is derived from Git's reachable
[one-way footer evidence](../../decisions/0002-one-way-git-evidence.md). Read-only output may report Git commits, while
Beads remains free of implementation, delivery, task, evidence, and bookkeeping commit mappings. Feature approval
continues to follow
[committed-content approval](../../decisions/0003-committed-content-approval.md),
and roots remain open until actual delivery as required by the
[root-open decision](../../decisions/0004-root-open-until-delivery.md).

No operation calculates a ready frontier. No compatibility operation runs during normal feature work. No documentation
surface becomes a workflow dashboard.

## Interfaces and data flow

The retained public commands gain narrow data/option changes:

```text
dstackctl alignment finish-plan AUDIT --plan-file PLAN.json
dstackctl setup doctor --delivery-mode merge|pr
dstackctl adopt apply LEGACY --remaining ID [--spec-ceremony ID ...] [classification flags ...]
dstackctl delivery cancel-pr-gate FEATURE --reason REASON
```

Alignment plan data flows from a temporary JSON file through strict parsing and canonicalization into the analysis
description and root digest metadata. No new plan-scaffold command is needed: Tier 1 writes this small object directly.
The old Markdown `alignment-plan` scaffold/validator and finish-plan `--summary-file` option are removed; Markdown
reconciliation records and their separate interfaces remain unchanged. Finish-plan, approval, reauthorization, and every
correction execution mutation independently resolve the configured target ref and require its exact Git commit ID to
equal the plan's `baseline_commit`. Approval and execution recreate plan bytes from the description and compare the
current correction content/graph on every invocation. The temporary input is not authoritative after finish-plan.

Adoption classification flows from explicit repeatable CLI selections first into a pure closed-world transformation
plan, then into a separate native execution boundary. No classification file is durable or accepted by the controller.
The execution phase creates/reuses replacements, redirects outgoing blockers and incoming external dependents in safe
order, verifies readiness-preserving postconditions, and only then supersedes. Beads receives only native issues,
relationships, closure reasons, comments for accepted uncertainty, and supersession.

Setup plan emits both the human-readable payload and canonical mutation object with `plan_sha256`. Apply retains the
existing digest-only interface, recomputes and canonicalizes the current complete mutation object exactly once, requires
its digest to equal the reviewed digest, and executes that same in-memory object. It never recomputes a second semantic
plan after comparison. The reviewed plan output remains ephemeral user data, not repository or dStack state.

Audit derives a candidate commit from the configured target search ref, reads blobs with direct `git show`-style
operations, and scans footer history ending at the candidate. Direct blob reads are preferred over a temporary audit
worktree because record parsing needs files, not a mutable checkout, and avoiding another cleanup boundary is smaller.

## Failure behavior

- Invalid alignment schema, unknown fields, unstable values, malformed dependency references, duplicate correction
  titles, changed/missing Git baseline, any correction content/parent/label/priority/dependency difference from the
  canonical plan, digest mismatch, or unidentified partial native closure fails before further authorization or
  execution mutation.
- An interrupted alignment transition remains unauthorized whenever pending is present, approved is absent/mismatched,
  the audit baseline differs, correction content/graph differs, or any native state is incomplete.
- Any terminal state or assignee outside exact open/unassigned rejects reauthorization before digest mutation. A changed
  terminal after reopening is reported and leaves implementation unauthorized.
- Adoption planning rejects foreign/root IDs, overlaps, omissions, unsupported item types, inadequate completion
  evidence without explicit accepted risk, unresolved decisions without a safe blocking/incorporated outcome, stranded
  preserved work, unknown incoming/outgoing external relationships, incompatible relationship translation, and invalid
  replacement reuse before mutation.
- Native adoption execution adds/verifies replacement and redirected incoming blocker edges before removing old edges or
  superseding. Any external dependent that would become ready prematurely stops the transition. Partial retries inspect
  native replacements, both relationship directions, and supersession; conflicts stop with observed facts and never
  infer a hidden mapping.
- A raced claim outside the requested scope is released and verified. Release failure reports ownership uncertainty and
  never reports success.
- Worktree removal failure retains evidence. Registration/status query failure is reported as `unknown`, not guessed.
  Cleanup errors remain secondary to primary delivery errors.
- Missing, duplicate, or ambiguous closeout footer commits; expected evidence not reachable from the candidate;
  unsupported delivery history; missing target ref; or missing candidate blobs fails audit revision consistency without
  fallback.
- Any setup mutation drift changes the recomputed canonical object's digest and requires a new plan review. Digest-only
  apply cannot compare unavailable source bytes; it compares SHA-256, executes the same recomputed object on a match,
  and stops on apply-time drift without expanding the operation set.
- Merge doctor does not fail for absent remote/GitHub. PR doctor fails with the specific missing capability.
- Documentation ambiguity lists exact paths and manual navigation/link action and prevents setup from claiming complete
  migration.
- PR-gate cancellation fails on missing/ambiguous/wrong-type/wrong-relation gates, empty reason, failed native
  postcondition, or observed Git mutation. Candidate invalidity alone is not an error for cancellation.
- Required validation that fails, times out, is interrupted, unexpectedly skips, or is replaced by weaker coverage
  remains blocking and is reported exactly.

## Security implications

Beads JSON, plan/classification files, issue content, refs, dependency records, paths, Markdown links, gate reasons, Git
history, and subprocess output are untrusted inputs processed with invoking-user privileges. Strict schemas reject
unknown/open-ended data. Paths remain repository-relative, normalized, and containment checked. Refs use native Git
validation, subprocess arguments remain structured, and option terminators are retained where supported.

Canonical JSON prevents ordering ambiguity but is not a trust signature. Human authorization still applies to the
displayed reviewed content. SHA-256 identifies content only. Accepted-risk adoption comments must not contain secrets.
Audit and cleanup reports may expose local paths and commit identities to the invoking user but are never published
automatically. Gate reasons are data, never shell syntax. No new network service, credential store, privilege boundary,
destructive Git operation, or secret-bearing persistent state is added. Current
[security guidance](../../security/index.md) remains authoritative.

## Compatibility and migration implications

The supported native boundary remains `bd version 1.2.2 (6c124203e)` and mdBook 0.5.4 as documented in
[compatibility](../../reference/compatibility.md). New alignment metadata keys are namespaced and affect only current
alignment molecules using the hardened approval commands. An alignment with closed authorization state and no canonical
identity fails closed and requires explicit reauthorization; normal commands do not repair it silently.

Adoption is already an explicit legacy boundary. Its classification input becomes stricter, but the command name and
native result remain. Existing category flags cannot authorize incomplete classification. Setup plan schema advances to
v2; an old digest/object is rejected and must be replanned. Doctor callers must select a delivery mode, preventing
accidental inference changes.

Direct fast-forward delivery and PR delivery that preserves the candidate as a remote-target ancestor remain supported.
Squash/rebase PR delivery and direct merge commits remain unsupported. Existing closed features with one unique
reachable closeout footer remain auditable without migration. Ambiguous historical features report limitations rather
than receiving stored commit mappings.

Documentation migration moves only mechanically identified content and never changes authored content on conflict. No
database, formula topology, Git history, or post-delivery bookkeeping migration is introduced.

## Validation strategy

Tests are behavior-first and precede implementation changes.

- Alignment tests validate canonical bytes against permutations of object, comment, dependency, newline, Unicode, and
  response ordering; verify the same exact `baseline_commit` at finish-plan, approval, reauthorization, claim,
  completion, and workstream finish; reject baseline movement and every correction content/parent/label/priority/blocker
  drift; and inject failure before/after baseline, description, pending, analysis, gate, approval, approved, and
  pending-clear checks or mutations. Same plan/baseline/graph converges; any changed authorization input requires
  reauthorization. CLI, fast, and acceptance fixtures use `--plan-file` with canonical JSON and reject the removed
  Markdown plan/`--summary-file` interface; reconciliation fixtures remain Markdown.
- Shared reauthorization tests cover every unsupported terminal state, assigned open tasks, concurrent terminal changes,
  digest ordering, actionable recovery, and post-reopen reread for both feature and alignment callers.
- Adoption planning tests cover strict common entry IDs, every literal classification, strategy-specific fields and
  specification selectors, unknown/missing IDs, verified and explicitly accepted incomplete history, blocking unresolved
  decisions, the initial incorporated blocker/root veto, complete outgoing external blocker and incoming external
  dependent inventory, compatibility decisions, and zero mutation on an invalid plan.
- Separate native adoption fast and real-Beads tests cover approved-design finalization, replacement reuse, internal
  blockers, outgoing external blockers, incoming external dependent redirection, supported context, ordering, approval
  dependencies, add-before-remove relationship order, interrupted retries, and supersession/root veto. A real unrelated
  external task blocked by legacy work must remain blocked on its replacement and cannot become ready prematurely.
- Claim tests use two simultaneously ready tasks and a race where the first is won elsewhere; no-selector accepts the
  second valid task. Explicit mismatch, foreign parent, bad label, multi-result, and failed release are covered in fast
  and supported real-Beads scenarios.
- Real-Git cleanup tests prove complete cleanup, retained registration/path/dirty evidence, primary-plus-secondary error
  composition, and no automatic deletion.
- Audit and delivery tests require the unique closeout-footer commit to equal candidate HEAD before delivery, reject a
  post-closeout candidate commit, deliver to `main`, remove branch/worktree, advance `main`, create conflicting
  documentation on an unrelated branch, and prove both records and footers come from the unique closeout candidate. PR
  merge-commit ancestry, missing, duplicate, later-only footer, and unsupported history fail as specified.
- Setup tests permute Beads, dependency, dictionary, traversal, and path ordering across canonical plans; equivalent
  sets have identical bytes/digests and every material mutation differs. Init and non-init plans differ; absent Beads
  cannot mutate without the reviewed initialization record. Digest-only apply derives one object, compares its SHA-256,
  executes that same object on a match, and rejects drift before mutation without claiming unavailable-byte comparison.
- Independent doctor tests cover healthy merge-only operation without origin or `gh`, actionable PR failures for remote,
  compatibility, auth, and gate capability, and every internal Python/CLI/skill/example/test caller supplying an
  explicit mode. Doctor has no dependency on migration-fixture completion.
- Three fixture suites prove conservative migration, byte preservation, non-overwrite, exact ambiguity reporting,
  blocked completion, manual correction, and rerun convergence.
- Cancellation recovery tests remove candidate branch/worktree or invalidate docs and prove native gate cancellation
  succeeds with unchanged Git; gate type, relation, uniqueness, reason, and postcondition failures remain blocking.
- Regression tests retain pending/approved feature design identity, native readiness/fan-in, active PR merge refusal,
  explicit replacement, partial delivery facts, verified release, untracked-file cleanliness, reachable footer evidence,
  documentation policy, and no Git mutation during finalization.

Release acceptance runs configuration parsing, Python compilation, Ruff, the repository's strict type and dependency
checks, all fast tests without unexpected skips, each real-Beads scenario separately, real-Git scenarios, actual mdBook
validation/build, documentation policy, candidate footer/path evidence, `git diff --check`, `git fsck --full`, bundle
verification, and clean-clone validation. Existing successful evidence is reused unless relevant files change.

## Documentation impact

### End user and operator

Update the [feature lifecycle](../../development/feature-lifecycle.md), [delivery guide](../../operations/delivery.md),
and [recovery guide](../../operations/recovery.md) for canonical alignment-plan review/retry, exact Git audit-baseline
verification, correction graph drift, terminal reauthorization failures, adoption classification, accepted-risk and
incoming-dependent handling, retained cleanup worktrees, immutable audit revisions, setup drift, explicit doctor modes,
conservative migration ambiguity, and Beads-only abandoned PR-gate cancellation. The
[CLI reference](../../reference/cli.md) documents the plan/classification files, doctor option, audit source fields, and
candidate-free cancellation.

Usage/configuration changes are local command options and strict temporary data schemas. No service deployment is
introduced. Upgrade behavior requires replanning old setup schema and explicit reauthorization for an alignment already
closed without canonical identity. Rollback uses the prior Git candidate and native Beads recovery described in the
recovery guide; no automatic history rewrite is added.

### Developer and reviewer

Update the repository contract, shared core skill,
[core principles](../../development/index.md),
[architecture](../../architecture/index.md),
[one-way Git evidence decision](../../decisions/0002-one-way-git-evidence.md),
[metadata and labels](../../reference/metadata-labels.md),
[compatibility](../../reference/compatibility.md),
[documentation policy](../../development/documentation.md), and [tooling](../../development/tooling.md) with the narrow
explicit-workflow-input exception, canonical serialization, complete authorization predicates, exact audit-baseline
revisions, correction graph drift, terminal safety, bidirectional adoption graph/result contracts, worktree retention,
immutable revision derivation, setup plan schema, delivery profiles and explicit internal callers, and real-boundary
validation.

Keep pure canonicalization and Markdown parsing independent of Pi/TUI concerns. Extract small shared helpers only where
alignment/feature transitions, audit/docs, or setup apply use the same concrete behavior. Existing module and command
names remain unless the narrow interfaces in this design require an option or data-file change.

### Future auditor

This design, the prior
[authority hardening record](../resolve-remaining-workflow-authority-findings/design.md),
accepted decisions, reconciliation record, behavior tests, and exact validation results preserve why each identity and
recovery boundary exists. Audit output reports the configured target search ref, derived immutable candidate revision,
derivation failure, and source consistency without storing a delivery commit or Bead-to-commit evidence mapping in
Beads.

Future review must detect regression if comments enter alignment identity, the Git audit baseline or correction graph is
not checked at execution, classification can omit executable descendants or incoming external dependents, a moving
target tip becomes the document source, canonical setup order changes digest, failed cleanup deletes evidence, doctor
infers mode, or candidate validation again blocks abandoned-gate cancellation.

## Risks and tradeoffs

- Canonical JSON is less comfortable to author than Markdown. A strict schema and temporary file make identity
  unambiguous; readable rendering may be emitted for review but is not another authoritative store.
- Using unique correction titles as plan-local dependency keys requires title uniqueness and rejects external correction
  blockers in schema v1. This avoids persisting generated IDs or introducing task-key metadata; title, content, or graph
  changes appropriately require reauthorization.
- Exact audit-baseline verification intentionally blocks alignment execution when the configured ref moves, even for an
  unrelated commit. The alignment must be reviewed against current reality rather than silently execute stale findings.
- Completing history from source/test/docs evidence still needs human judgment. Explicit accepted-risk authorization and
  a concise native comment preserve the irreducible decision without turning comments into a ledger.
- Strict closed-world adoption may leave a legacy root unsuperseded when native reparenting or type-compatible blocking
  cannot preserve work. That visible outcome is safer than stranding tasks.
- Requiring a unique reachable closeout footer makes ambiguous older history an audit limitation. Persisting a commit
  mapping would make more cases pass but violate Git/Beads decoupling.
- Direct blob reads need a small revision-aware reader for local-link validation. This is smaller than creating another
  temporary worktree and avoids cleanup risk, but validation must clearly distinguish missing-at-revision from missing
  in the caller checkout.
- Exact setup plans are larger than ID-only normalization lists. The additional bytes are ephemeral reviewed data and
  remove silent plan/apply drift.
- Mandatory doctor mode is a narrow compatibility change, but it eliminates unstable hidden inference.
- Retained failed-cleanup paths consume disk until an operator resolves them. Preserving evidence and preventing data
  loss outweigh automatic reclamation.

## Rejected alternatives

- Hash an unordered set of alignment comments: unrelated discussion, ordering, authors, timestamps, and retries would
  make identity ambiguous.
- Store the alignment plan in both a comment and metadata JSON: that creates two writable plan stores. The analysis
  description is the sole plan surface; metadata stores only digests.
- Include Beads task IDs or status in canonical plan bytes: generated/transient values would change identity without
  changing reviewed corrective intent.
- Reopen terminal work automatically: it can override active closeout/landing authority.
- Treat incomplete legacy history as completed by default: it silently discards potentially real work.
- Convert unresolved decisions into generic implementation tasks: it weakens the authorization boundary and hides a
  blocking product decision.
- Supersede the legacy root even when preserved work becomes inaccessible: it violates native reachability and
  readiness.
- Persist an adoption map or translated dependency graph: native supersession and relationships are the audit evidence
  and source of truth.
- Preselect the first ready task before native claim or retry stale choices: native atomic claim already owns selection.
- Recursively delete temporary parents after failed `git worktree remove` or run broad prune: either can destroy
  evidence or affect unrelated registrations.
- Audit the current target tip or caller checkout: both can contain post-delivery changes and produce a false historical
  view.
- Store the derived delivered commit in Beads: rewrite-safe one-way footer evidence already lets Git reconstruct the
  boundary.
- Hash insertion-order JSON or a presentation payload containing absolute paths: equivalent mutation sets would vary by
  process, platform, and checkout.
- Recompute broad setup normalization after digest comparison: it can apply unreviewed changes.
- Infer doctor mode from origin or `gh`: incidental environment state would change health semantics.
- Guess documentation destinations by headings, filenames, or a model: wrong semantic placement is worse than explicit
  manual correction.
- Require candidate validation to cancel an abandoned gate: invalid/missing candidates are a primary recovery use case.
- Add services, transactions, plugins, state stores, or a broad module rewrite: none is necessary for the demonstrated
  boundaries.

## Open or intentionally deferred decisions

All clarification boundaries are resolved: the alignment plan is canonical JSON in the analysis description and directly
binds the exact Git `baseline_commit` used by the audit; execution rereads that revision and the exact approved
correction content/graph; every adoption classification has a precise native outcome and evidence rule; outgoing
external blockers and incoming external dependents are planned and translated before supersession; immutable audit
revision is the unique reachable closeout-footer candidate under supported delivery ancestry; setup identity is compact
sorted-key canonical JSON over the complete exact mutation set; digest-only apply compares only the recomputed SHA-256
and executes the same object; and doctor mode is independent and explicit at every caller.

Direct `git show`-style blob reads are selected for closed audit because they avoid a second temporary-worktree cleanup
boundary. Unique correction titles are selected as plan-local dependency keys to avoid generated-ID metadata. The
explicit classification flags and explicit doctor-mode interfaces are selected as the smallest unambiguous command
changes.

Helper extraction remains conditional on concrete duplication exposed during implementation and is not a scope decision.
If pinned Beads experiments show that a requested preserved-work reparent or nonblocking relationship is not supported,
adoption must select recreation, keep the legacy root unsuperseded, or stop; it must not emulate native state. No
product or architecture decision remains open for authorization.
