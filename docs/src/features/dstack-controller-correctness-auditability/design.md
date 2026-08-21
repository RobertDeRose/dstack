# Feature design

## Goal

Make the dStack controller fail closed and remain auditable at lifecycle, selection, and delivery boundaries. The same
repository state must produce the same result without a dStack state store, while Beads remains authoritative for work,
ownership, dependencies, gates, and completion and Git remains authoritative for source and evidence.

## User-visible behavior

- A changed approved design is rejected at every implementation and delivery boundary with an actionable request to
  review the specification again.
- Claims and finishes use Beads' native ownership semantics. Reclaiming work by its current owner is idempotent; another
  owner's claim or finish fails without a dStack ownership ledger.
- Delivery refuses a completed feature when any normal closed implementation task lacks reachable `Beads: <id>`
  evidence. A task explicitly closed as requiring no repository change is accepted through its native close reason.
  History rewrites remain valid because the audit searches current reachable commits rather than storing commit hashes.
- A task that intentionally changes no repository content must use an explicit no-repository-change option and a
  non-empty reason. The reason and its no-change classification are stored only through the native Beads close reason;
  the old ambiguous bypass is removed.
- Feature skills pass their selected root explicitly. Automatic selection works only from the matching feature worktree,
  and ambiguous or unrelated contexts fail instead of silently acting on another feature.
- Repeated planning or initialization of a normal planned Beads epic with the same feature identity reuses one planned
  source, preserves native external dependencies, and creates at most one current workflow molecule.
- Every feature design uses the mdBook path `docs/src/features/<slug>/design.md`; nonconforming explicit paths fail.
- Documentation checks reject dStack lifecycle bookkeeping while allowing ordinary domain language such as a document
  describing a blocked request.
- Delivery inspection reports the actual target branch ref. It never presents the candidate worktree as the target
  merely because the target branch has no checked-out worktree; merge operations fail closed when a writable target
  worktree is unavailable.

## Non-goals

- No dStack database, state file, ownership ledger, Git-SHA mapping, scheduler, score, coverage threshold, approval
  matrix, or semantic documentation classifier.
- No new lifecycle state or new public workflow entry point. Existing controller commands and skills are tightened in
  place.
- No general-purpose planning database or duplicate roadmap representation.
- No redesign of Beads formulas, Git, or remote hosting behavior beyond the checks needed at existing dStack boundaries.
- No unrelated product behavior or domain-document vocabulary is standardized.

## Existing patterns and reuse

- Reuse `BeadsClient`, `feature_view`, native `bd update --claim`, native close reasons, dependencies, gates, and
  worktree support instead of mirroring their state in Python.
- Reuse the approved-design digest already stored in namespaced Beads metadata and the existing `file_sha256` helper.
  The controller should centralize the guard rather than adding per-command digest logic.
- Reuse Git's `rev-parse`, `merge-base`, worktree records, commit footers, and reachable history for target identity,
  ancestry, and evidence.
- Extend the current fake-Beads controller tests and the supported real-Beads integration boundary. Keep pure controller
  decisions independent of Pi/TUI APIs and add no dependency.
- Keep the current JSON envelope and command names. New response fields may be additive, but existing successful and
  failure boundaries remain machine readable.

## Design

### Boundary validation and ownership

Use one approved-design validation path and invoke it before claiming or finishing implementation work, claiming or
finishing closeout, and producing or executing delivery decisions. It recomputes the design file from the feature's
registered worktree and compares it with the approved digest before any state transition. A mismatch fails without
closing or claiming work and uses the existing re-review wording.

Use Beads' native claim operation for every non-closed task, including tasks already marked `in_progress`. The shared
claim helper must not return an `in_progress` task without asking Beads to verify ownership. Finish operations claim
their task before closing it so a different owner cannot bypass the native ownership check. Native Beads errors are
returned; no owner is copied into metadata or comments.

### Evidence and explicit no-change completion

At delivery boundaries, derive implementation-task evidence from the candidate branch's current reachable commits.
Require every normally closed implementation task to have a reachable footer and reject unknown footer IDs, while
retaining support for multiple commits and rewritten commit identities. A task closed through the explicit
no-repository-change path is the only exception; its stable native `no-repository-change: <reason>` close-reason marker
is checked instead of a Git footer. The resulting audit is computed in memory and exposed in the existing inspection
result; no mapping is persisted.

Replace `--allow-no-commit` on feature and alignment task completion with `--no-repository-change --reason <text>`. The
option is valid only with a non-empty reason and closes through the native Beads reason using the
`no-repository-change: <reason>` marker needed by delivery audit. A normal task still requires a reachable footer. A
no-change completion does not make Git content or a workflow bookkeeping commit appear in the candidate.

### Truthful selection and planned-feature reuse

The start, review, implementation, and closeout skills retain the selected feature in conversation and pass it to every
controller invocation. The controller may infer a feature only when its working directory is the registered
`feat/<slug>` worktree; from the repository root or another worktree, an omitted selector is an error. Exact IDs, slugs,
and normalized feature titles remain supported, and ambiguity is reported rather than guessed.

Treat a normal Beads epic labeled `dstack:feature-idea` and `feature:<slug>` as a durable planned source. Resolve it by
ID, slug, or title, update/reuse the matching source rather than creating a duplicate, and carry its description,
acceptance intent, priority, and non-descendant blocking dependencies into the current workflow. This upsert extends the
existing feature initialization/resolution path; planning continues to use native Beads creation and updates rather than
gaining a new public planner command. Pouring the current molecule and superseding the source remain one idempotent
transition after branch/worktree creation succeeds. Existing current molecules are returned unchanged.

### Design paths and documentation policy

Resolve every new feature design to `docs/src/features/<slug>/design.md`. Reject a command-supplied path that does not
match this mdBook convention. Validate the resolved path as a repository-relative file without parent traversal or
symlink escape.

The documentation guard examines changed documentation lines for structured dStack bookkeeping such as lifecycle status
fields, Beads/gate identity, branch/worktree or commit records, and next-command instructions. It does not reject
arbitrary words such as `blocked`, `completed`, or `review` when they are ordinary domain prose or code examples; only
the documented bookkeeping forms are forbidden. Durable planned/implemented/deprecated product context remains allowed
when it is part of a real feature change.

### Delivery target identity and compatibility

Report `target_head` by resolving the configured target branch ref directly. Use a registered target worktree only for
operations that must mutate that branch, such as fast-forward merge. Inspection and preflight must not fall back to the
candidate worktree; retain the `target_worktree` response field with a null value when no target worktree is registered.
Merge then fails closed until a writable target worktree exists. Delivery continues to reject non-ancestral,
merge-commit, stale-remote, and tracked-runtime candidates through the existing validation path, with footer and design
checks added before the result is accepted.

Keep the existing JSON envelope, selector forms, feature lifecycle, and Beads-native formulas. The intentional CLI
compatibility change is the removal of the ambiguous no-commit bypass; skills and tests use the explicit option. All
other callers receive deterministic nonzero failures rather than a silently changed target or feature.

## Failure / security / compatibility behavior

- Design drift, missing design files, invalid paths, ambiguous selectors, missing worktrees, missing footer evidence for
  normal tasks, unknown footer IDs, stale targets, and non-fast-forward delivery all fail before the relevant mutation.
- A competing owner cannot claim or finish a task; the current owner may repeat the claim safely. Beads remains the
  authority for the race boundary.
- A malformed or empty no-change reason is rejected before Beads is changed.
- Path resolution rejects absolute paths, parent traversal, and symlink escapes. The controller does not execute content
  from a selected design file.
- The controller never writes Git hashes or transient lifecycle data to Beads. It preserves native Beads errors and
  JSON-envelope behavior for callers.
- Repositories migrate feature designs and stable metadata to the mdBook path; new nonconforming explicit paths fail
  before Beads mutation.

## Validation strategy

- Add behavior-first fake-Beads tests for design drift at each listed boundary, same-owner and competing-owner claims,
  finish ownership enforcement, rewritten and missing footer evidence, unknown footer rejection, explicit no-change
  reasons and delivery exemption, selector passing and wrong-worktree rejection, planned source reuse/dependency
  preservation, and target-ref reporting.
- Add tests for the required mdBook feature path and a domain document containing legitimate `blocked`/`review`
  vocabulary. Cover invalid and symlink-escaping design paths.
- Exercise the supported real `bd` binary in JSON-envelope mode for native claims, gates, dependencies, fan-in, and
  delivery behavior when available.
- Run focused controller tests, the full repository suite, `git diff --check`, Python compilation, and the repository's
  existing setup/formula checks. Do not add a coverage-percentage gate.

## Documentation impact

- **End user/operator:** document only the observable selector, no-change completion, design-drift, and delivery failure
  behavior in existing workflow reference material; no separate workflow-state document is needed.
- **Developer/reviewer:** update the controller/skill guidance and tests to make native ownership, digest checks,
  evidence, target identity, and the mdBook documentation layout durable maintenance constraints.
- **Future agent/auditor:** preserve the feature design, Beads acceptance criteria, rewrite-safe footer audit, and
  regression tests as the durable evidence of why each fail-closed boundary exists; no agent-only instructions or state
  file is required.
