# Resolve remaining workflow authority findings

## Planned intent

Resolve the remaining approval, delivery, claim-recovery, compatibility, and closed-feature audit gaps found after the
previous authority-hardening delivery. The interrupted approval defect is release-blocking because native authorization
can currently be rebound to content that the human gate did not review.

## Planned acceptance

Approval persists and verifies pending content identity before native state changes, retries only the same content, and
exposes approved context only after promotion completes. Direct delivery refuses an associated PR gate until an explicit
cancellation preserves native audit context. Delivery finalization errors report the already-delivered Git state.
Unexpected claims are released and verified, initial lifecycle claims use native readiness, delivered audits recover
footer evidence from the target branch after cleanup, and installation guidance preserves the exact supported Beads
build boundary.

## Feature summary

This feature closes five authority-boundary gaps without adding a workflow store. It introduces a temporary pending
design digest in Beads metadata, changes PR-gate cancellation from an implicit delivery side effect into an explicit
native operation, unifies post-delivery failure facts, verifies claim release, and derives cleaned-up feature evidence
from reachable target history. It also makes the existing exact Beads build policy operationally clear.

The work refines the guarantees established by the
[previous hardening design](../harden-workflow-authority-auditability/design.md),
the [committed-content approval decision](../../decisions/0003-committed-content-approval.md), and the
[one-way Git evidence decision](../../decisions/0002-one-way-git-evidence.md).

## User intent

Operators and agents must be able to retry approval and delivery commands after process, Beads, or storage failures
without guessing which design was approved, which delivery mode remains authoritative, whether Git was already
delivered, or who owns a raced claim. A delivered feature must remain auditable after its normal branch and worktree
cleanup.

## Goals

- Bind every approval attempt to committed design bytes before closing any native authorization state.
- Require explicit human intent before replacing PR delivery with direct merge.
- Make post-delivery Beads failures unmistakable and actionable without rewriting Git.
- Restore both status and ownership after every unexpected native claim.
- Use native readiness for open specification and alignment-analysis claims.
- Recover expected footer evidence from delivered target history after feature cleanup.
- Keep the exact acceptance-tested Beads build policy and explain its PATH consequence prominently.

## Non-goals

- No dStack database, transaction log, approval manifest, delivery state, readiness graph, claim ledger, scheduler, or
  persistent audit cache.
- No Git commit hashes in Beads and no requirement to retain delivered feature branches or worktrees.
- No automatic Git reset, revert, history rewrite, force-close, or post-delivery bookkeeping commit.
- No automatic cancellation of PR gates merely because direct merge was requested.
- No semantic-version compatibility claim for Homebrew Beads builds.
- No rewrite of the previously delivered molecule or unrelated formula, documentation, review, or GitHub-polling
  behavior.

## User-visible behavior

`feature approve-spec` becomes interruption-safe. Inspection may show a pending design digest while approval is
incomplete, but implementation remains unauthorized until the approved digest matches committed design bytes, all native
authorization states are closed, and pending metadata is absent.

`delivery merge` fails before touching the target when an unsuperseded PR gate still blocks the root, including a closed
gate whose blocking relationship is still active. A new `delivery cancel-pr-gate <selector> --reason <reason>` operation
explicitly resolves the gate when needed, replaces its blocking relationship with a nonblocking native relation, records
the reason, and verifies that direct delivery is unblocked. It does not close or modify the GitHub pull request.

When direct or PR delivery has already happened but root finalization fails, the command reports `delivery_completed`,
`previous_target_head`, `delivered_target_head`, `observed_target_head`, `root_status`, `finalization_error`, and
`mutation_uncertain`. Recovery remains a separate, explicit native Beads or Git action as described in the
[recovery guide](../../operations/recovery.md).

Feature audit reports removed feature-branch/worktree context separately from Git evidence. For a delivered root,
expected implementation and lifecycle footers remain available from the configured target branch when reachable.

## Requirements

1. Approval reads the validated committed design digest and the root's pending and approved digest metadata before
   native authorization mutation.
2. With no approved digest, approval may create `dstack.pending_design_sha256` only while no native authorization state
   is closed. It must reread and verify the pending value before closing specification, human gate, or approval.
3. A matching pending digest may resume and converge the same approval. A mismatched pending digest requires explicit
   reauthorization. Any closed native authorization state with neither digest fails closed.
4. Promotion writes and verifies the approved digest, then clears pending and verifies the final approved predicate.
   Both matching keys represent an incomplete promotion and do not authorize implementation until pending is removed.
5. Reauthorization unsets approved first, then pending, before reopening native authorization. Every partial boundary
   remains unauthorized and retryable.
6. Direct merge queries root-associated PR-gate state immediately before Git mutation and refuses every unsuperseded
   blocking PR gate regardless of open or closed status.
7. Explicit PR-gate cancellation requires one unique active gate and a nonempty reason. It closes an open gate with the
   cancellation reason, records the decision when the gate was already closed, removes the blocking dependency, adds a
   nonblocking `relates-to` relationship, and verifies the resulting gate/root graph.
8. Direct and PR finalization catch root-close failure separately, reread the root when possible, inspect current Git
   state, and report the required partial-delivery fields. No automatic Git recovery is permitted.
9. One shared release helper sets an unexpectedly claimed issue to `open` with an empty assignee, rereads it, and
   requires open/unassigned state. The pinned Beads build has no native unclaim command; real-binary review verified
   that `bd update <issue> --status open --assignee ""` clears ownership.
10. Unexpected implementation claims, unexpected lifecycle-step claims, and newly claimed terminal fan-in races use that
    release helper. Multiple unexpected results are all released or reported as uncertain.
11. Open feature specification and project-alignment analysis steps use native ready-and-claim with exact step identity.
    Existing ownership checks remain authoritative for already claimed work.
12. Delivered feature audit scans the configured target ref once, filters the footer map to expected specification,
    implementation, and closeout work, honors explicit no-repository-change completion, and ignores unrelated feature
    footers rather than treating normal target history as this feature's candidate range.
13. README installation text names the exact `bd --version` output and tells operators to use the mise/aqua-installed
    binary or ensure it precedes a separate Homebrew binary on `PATH`. The supported version check is not broadened.

## Existing patterns and reuse

The implementation reuses the existing `root_metadata_value`, committed design hashing, native close/reopen helpers,
`pr_gate_state`, `resolve_gate_if_needed`, Beads dependency primitives, `commit_footer_ids`, target-ref validation, and
single-invocation read-cache invalidation. The current scripted client and two real-Beads scenarios remain the
validation boundaries.

The explicit cancellation operation extends the existing register/replace/ unique PR-gate model documented in
[delivery authority](../../operations/delivery.md). The verified release helper replaces three status-only or missing
cleanup paths rather than adding per-caller recovery logic. Delivered audit reuses the one-process Git log parser; it
does not create another evidence format.

No new dependency, service, protocol, persistence layer, background process, or interface hierarchy is necessary.

## Proposed design

### Two-phase content authorization

The pending digest is a write-ahead content identity, not approval state:

```text
validate committed design and compute digest
  -> read approved, pending, and native authorization states
  -> reject inconsistent or different identity
  -> write pending when beginning a new safe attempt
  -> reread pending and verify exact digest
  -> converge specification, human gate, and approval milestone
  -> reread and verify every native state
  -> write approved digest and verify it
  -> clear pending digest
  -> reread complete authorization predicate
```

Read-side authorization requires all of the following:

```text
pending digest is absent
approved digest equals committed design digest
working file equals the committed design blob
specification is closed
exact human gate is closed
approval milestone is closed
```

If approved and pending both match after an interrupted promotion, retry verifies native state and clears pending. If
they differ, or closed native state has no content identity, approval fails and instructs explicit reauthorization.
Reauthorization invalidates approved context before changing native state.

### Explicit delivery-mode replacement

PR-gate state distinguishes all associated gates from active blockers. An active PR gate is unsuperseded and still
connected to the root through a blocking relationship or supported native waiter representation. A cancelled gate
remains associated only through a nonblocking native relation, so audit context survives without blocking direct
delivery or requiring custom metadata.

`delivery cancel-pr-gate` requires a unique active PR gate. For an open gate it uses native gate resolution with the
supplied reason. For an already closed active gate it preserves the existing close result and records the explicit
mode-change reason as irreducible decision evidence. It then removes only the root/gate blocking edge, adds the
nonblocking relation if absent, rereads both issues, and verifies that no active blocker remains. Ambiguous gates still
use `delivery replace-pr` before cancellation; cancellation never guesses among multiple human-created gates.

### Partial-delivery facts

One finalization helper owns both close-failure and post-close Git-invariant reporting. The caller supplies the
pre-delivery target, authoritative delivered target, expected local head, and status snapshot. Root close is wrapped by
itself because it may mutate before returning an error. On error, best-effort rereads cannot replace the primary
failure; unavailable facts are reported as unknown and `mutation_uncertain=true`.

Direct merge sets `delivery_completed=true` only after the target reaches the candidate. PR finalization sets it because
the closed native PR gate and remote target ancestry have already proven delivery. The helper never rewrites Git.

### Verified claim release

A single helper performs the pinned native fallback:

```text
bd update issue --status open --assignee ""
  -> bd show issue
  -> require status=open and assignee absent or empty
```

Callers release every issue newly claimed by an operation whose exact-result postcondition failed. Failure to release
identifies the issue and leaves claim ownership explicitly uncertain. The helper is not used for an issue that was
already in progress before the operation.

### Delivered-history evidence

When the conventional feature worktree exists, current candidate audit remains unchanged. When it is absent and the root
is closed, audit validates the configured target branch and runs the existing footer parser against that reachable ref.
It selects only expected feature work IDs plus the specification and closeout IDs, reports missing expected evidence,
retains all matching commits for each expected ID, and treats unrelated target history as unrelated. The report marks
branch/worktree removal as cleanup context rather than an absence of evidence.

## Architecture consistency

The design follows the [dStack architecture](../../architecture/index.md) and
[core principles](../../development/index.md): Beads owns native gates, dependencies, readiness, claims, and completion;
Git owns committed design bytes, footers, reachability, and delivery; the controller queries and verifies both without
persisting custom state.

The pending digest is the minimum durable identity required across a nontransactional approval boundary. It is content
metadata in Beads, not a commit identity, task graph, approval ledger, or new lifecycle state. Native blocking and
nonblocking relationships express delivery authority and retained context. Audit remains stateless and recomputes
evidence on every invocation.

## Interfaces and data flow

The public mechanical CLI gains:

```text
dstackctl.py delivery cancel-pr-gate <selector> --reason <text>
```

The existing package commands remain stable. The feature lifecycle skill may invoke cancellation only after explicit
user direction to switch from PR to direct delivery. [CLI reference](../../reference/cli.md) and
[feature lifecycle](../../development/feature-lifecycle.md) describe the new failure and recovery boundary.

Beads metadata gains one temporary namespaced key documented alongside the approved digest in
[metadata and labels](../../reference/metadata-labels.md):

```text
dstack.pending_design_sha256
dstack.approved_design_sha256
```

Data flows only through native Beads JSON and Git commands. Cancellation uses native gate resolution and dependency
relationships. Claim recovery uses native update and authoritative reread. Delivered audit uses one reachable Git log
and existing footer parsing. Error output keeps the current JSON error envelope and includes stable named facts in its
error detail rather than adding a packet or persistent recovery object.

## Failure behavior

- A different pending digest, different approved digest, or native closure with no content identity fails before further
  approval mutation.
- Failure to write or verify pending prevents every native authorization close.
- Failure after native closure leaves pending identity, so only the same design may resume. Failure after approved write
  leaves pending present, so read-side authorization remains false until retry clears it.
- Reauthorization failure after approved invalidation cannot authorize implementation; retry derives remaining metadata
  and native state again.
- Any active PR blocker, including a closed unsuperseded gate, stops direct merge before target worktree mutation.
- Cancellation with no gate, multiple gates, empty reason, relation mutation failure, or failed postcondition reports
  the observed graph and does not run merge.
- Root-close timeout, storage error, malformed response, or partial mutation after delivery reports delivered Git facts
  and uncertainty. Root reread failure does not hide completed delivery.
- Claim-release failure never reports restoration. It names every ownership state that could not be verified.
- Missing target ref or missing expected footer evidence remains an audit issue; audit does not search arbitrary refs or
  store a fallback mapping.

## Security implications

Digests, refs, selectors, gate reasons, issue JSON, and repository history remain untrusted boundary data. Existing path
containment, native Git ref validation, structured subprocess argument arrays, exact issue/gate identity checks, and
postcondition rereads continue to apply. Cancellation reasons are data and are never executed.

Partial-delivery reports expose local refs, commit identifiers, issue status, and errors to the invoking user,
consistent with existing local audit output. They are not published automatically and must not contain credentials. The
feature adds no network access, credential store, privilege boundary, secret handling, or destructive Git operation.

## Compatibility and migration implications

Current open molecules need no topology rewrite. New approval logic reads the new pending key when present and otherwise
begins only from a safe native state. A workflow already left with closed authorization state and neither digest fails
closed and requires explicit user-authorized reauthorization; normal commands do not infer or repair historical
approval.

The exact Beads support boundary remains `bd version 1.2.2 (6c124203e)` as documented in
[compatibility](../../reference/compatibility.md). Specification review against that binary confirmed that an empty
`--assignee` clears claim ownership and that gate resolution, blocking-edge removal, and `relates-to` preserve native
state without custom metadata. Homebrew builds with a different literal version output remain unsupported even when
their semantic version is 1.2.2.

No database migration, formula change, branch migration, Git history rewrite, or post-delivery commit is required.

## Validation strategy

Tests precede controller changes and assert observable behavior.

- Approval protocol tests inject failure before and after every metadata/native mutation, especially after all native
  states close and before approved digest persistence. Same-design retry converges; changed-design retry and missing
  identity fail closed; both matching keys remain unauthorized until pending is cleared.
- Delivery tests prove open and closed active PR gates prevent target-head change, explicit cancellation preserves a
  nonblocking relation and reason, ambiguous cancellation fails, and cancellation followed by merge succeeds.
- Direct and PR finalization tests inject close timeout, storage failure, malformed response, partial close mutation,
  and reread failure. Every error contains all required facts and leaves Git untouched after delivery.
- Claim tests cover wrong implementation singleton, multiple unexpected claims, wrong lifecycle step, terminal fan-in
  race, assignee clearing, reread failure, and blockers on feature specification and alignment analysis.
- Audit tests fast-forward a candidate, remove its feature worktree and branch, and verify expected footer evidence from
  the target while unrelated footer history is ignored.
- Package/documentation tests require the exact pinned-binary README guidance, pending metadata contract,
  delivery/recovery behavior, and CLI help.
- The supported real-Beads contract proves assignee clearing and cancellation relationship behavior. The smoke scenario
  proves the critical interrupted approval, blocked direct merge, explicit cancellation, and cleaned-up audit boundaries
  where practical.
- Closeout runs the focused fast suite, both separate real-Beads scenarios, documentation validation/build,
  parser/compile/static checks, `git diff --check`, `git fsck`, bundle verification, and clean-clone checks required by
  the [testing contract](../../development/tooling.md).

## Documentation impact

### End user and operator

Update README installation requirements and the [delivery guide](../../operations/delivery.md) with the pinned-binary
PATH rule, active PR-gate merge refusal, explicit gate cancellation, and the distinction between cancelling dStack's
gate and changing a GitHub pull request. Update the [recovery guide](../../operations/recovery.md) with named
partial-delivery facts and separate native recovery actions. No configuration, service deployment, data migration, or
automatic rollback is introduced.

### Developer and reviewer

Update the [architecture](../../architecture/index.md),
[feature lifecycle](../../development/feature-lifecycle.md),
[CLI reference](../../reference/cli.md), and [metadata reference](../../reference/metadata-labels.md) for the pending
digest, final authorization conjunction, active-versus-related PR gates, verified claim release, and delivered-history
fallback. Controller and compatibility behavior remain small stateless helpers with real-boundary evidence.

### Future auditor

This design, its reconciliation record, the
[committed-content approval decision](../../decisions/0003-committed-content-approval.md),
and behavioral tests preserve why pending identity is necessary and why cancelled gates remain natively related.
Stateless audit output must distinguish removed worktree/branch context from missing evidence and retain validation
limitations without storing commit hashes or transient workflow state.

## Risks and tradeoffs

- One additional temporary metadata key increases the approval state space. The strict read-side conjunction and
  convergent retry table keep every partial state unauthorized.
- Replacing a blocking edge with `relates-to` depends on pinned Beads relationship behavior. Real-binary acceptance is
  required and the operation verifies its postcondition.
- Scanning all history reachable from the target is proportional to repository history. One Git log is the simplest
  stateless solution; optimize only if measured repository cost becomes material.
- Stable named facts embedded in the existing error detail are less structured than a new typed error envelope, but
  preserve CLI compatibility and avoid a speculative protocol. A separately reviewed interface change can add fields if
  consumers demonstrate a need.
- A closed PR gate can remain an active blocker until explicitly cancelled. This is intentionally stricter than
  inferring delivery mode from gate status.

## Rejected alternatives

- Writing only the approved digest after native closure cannot identify the content already reviewed after interruption.
- Writing the approved digest before native closure can make incomplete native authorization appear valid.
- Inferring content from closed gates, current branch state, timestamps, or comments is ambiguous and fails the
  authority model.
- Silently resolving, deleting, or ignoring PR gates during merge overrides human delivery authority or destroys audit
  context.
- Automatically resetting or reverting delivered Git after Beads failure risks data loss and violates the delivery
  invariant.
- Keeping feature branches forever or storing Git commit hashes in Beads creates unnecessary coupling and stale state.
- Supporting every semantic Beads 1.2.2 build without real acceptance evidence broadens compatibility beyond the tested
  contract.
- Adding a typed recovery packet, transaction service, or audit database is unnecessary for deterministic local
  reporting.

## Open or intentionally deferred decisions

All consequential product and architecture decisions are resolved for implementation. The native Beads experiment
selected resolve/remove-blocker/ relate for PR-gate cancellation and verified explicit status-plus-empty-assignee claim
release. Target-history audit selects only expected feature footer IDs from the configured reachable target ref. If
implementation evidence contradicts one of those pinned behaviors, work stops for specification reauthorization rather
than substituting custom state or broad compatibility.
