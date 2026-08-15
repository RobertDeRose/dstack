---
name: close-feature
description: Finalize a completed Beads feature by reconciling documentation, validating delivery, recording implementation, reviewing drift, and executing `pr`, `merge`, or `ready`. Use when asked to close a feature, prepare it for delivery, or reconcile implementation and documentation after its implementation coordinator closes.
metadata:
  version: "0.11.3"
allowed-tools: Read Glob Grep Edit Write Bash Task AskUserQuestion
---

# Purpose

Use this skill after the lifecycle implementation coordinator closes. Accept the same human feature selectors as
`/start-feature`. It converts delivered code into reconciled, validated, auditable product state. Resolve `<core-dir>`
as the installed `../dstack-core` skill directory.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

## Startup version evidence

Before the first workflow mutation, follow
[`../dstack-core/references/SKILL-VERSION.md`](../dstack-core/references/SKILL-VERSION.md) for `close-feature`. After
read-only feature resolution, capture the exact one-line output and append it to the selected root's Beads notes before
reconciliation or delivery mutation. A `stale` result warns with `npx skills update`; `unavailable` records that no
freshness claim was made and does not block offline work. Establish `workflow_run_id` before this diagnostic, using the
harness value or one created once for this session. If installed skills are refreshed, stop this session; continue only
from a new session that records an explicit rebind.

Delivery authority:

- Invocation authorizes local reconciliation, validation, workflow commits, and Beads updates for the selected feature.
- Only explicit `pr` mode authorizes pull-request creation. Only explicit `merge` mode authorizes merge and post-merge
  worktree removal. `ready` and no-action mode authorize neither.
- Merge mode authorizes a fast-forward-only merge by default. A merge commit is authorized only when the target
  repository's `AGENTS.md` explicitly states that merge commits are accepted.
- The workflow never force-pushes, deletes a remote branch, bypasses hooks, or removes a worktree before a confirmed
  merge.
- Close-review subagents are read-only.
- Merge mode authorizes bounded reconciliation of append-only `.beads/interactions.jsonl` rows for the selected feature
  molecule, plus separately identified work whose authoritative dependency lineage reaches that molecule through only
  `discovered-from` or `parent-child` edges, and the two interaction-only workflow commits described below. It never
  authorizes discarding, including, or rewriting unrelated rows or paths.

## Shared native Beads authority

Read [`../dstack-core/references/INTERACTION-BOUNDARY.md`](../dstack-core/references/INTERACTION-BOUNDARY.md) before any
delivery mutation. Native linked-worktree Beads authority is shared; `bd -C` is not an isolation boundary. Run
contiguous Beads reconciliation and delivery mutations under `beads-workflow-lock.py`. Before any close-out Beads
mutation in the base worktree, run `reconcile-beads-interactions.py preflight`; inspect foreign rows without mutation
when it fails. A busy lease, foreign interaction row, or snapshot race blocks delivery. Do not close delivery/root until
the guarded post-merge finalizer has passed.

## Supported Actions

- `pr`: create a pull request after successful close-out.
- `merge`: merge after successful close-out and finalize the feature.
- `ready`: leave the feature ready without PR or merge.
- no action: complete close-out, then ask the user to choose `pr`, `merge`, or `ready`.

## Execution

## 1. Activate and Inspect

Run `bd prime`, then resolve the supplied feature selector read-only. Immediately after obtaining its root ID and before
any claim, note, or other mutation, run `<core-dir>/scripts/migrate-review-topology.py guard --root-id <feature-root>`
with `--controller-topology-version 3`. A newer marker or unmigrated old review kind fails closed; only the
canonical-primary- worktree migrator owns topology mutation and old approval never transfers. When the selector is
omitted, infer it only from an active `feat/<slug>` branch. If the current branch is not a feature branch, stop and
require a selector rather than closing unrelated ready work:

```bash
branch=$(git branch --show-current)
feature_selector=${branch#feat/}  # only when branch matches feat/*
uv run <core-dir>/scripts/resolve-feature.py "<feature-selector>" --json
bd show <resolved-root-id> --json
```

Use the returned root ID for Beads operations and its canonical `<slug>` reference for worktrees, reports, and delivery
commands. Resolve `docs_reconcile_id`, `validation_id`, `review_implementation_integrity_id`,
`review_delivery_integrity_id`, and `delivery_id` from root metadata. Query the full molecule or child list only to
repair missing metadata. Activate and verify `feat/<slug>`. Inspect commits, implementation, tests, and changed files
before deciding whether documentation is accurate.

Continue only after all lifecycle IDs resolve, the active worktree is `feat/<slug>`, the implementation coordinator is
closed, and no open `migration:reconciliation` task blocks close-out. Before the startup-version note or any other
close-out Beads mutation, resolve the canonical base worktree and run the shared interaction preflight. If it fails,
inspect the appended rows without mutation and stop with delivery/root open:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py preflight \
  --worktree <base-worktree> --root-id <root-id>
```

## 2. Reconcile Documentation

Claim the documentation-reconciliation step. Compare delivered behavior with:

- feature `design.md`;
- every exact page named in Documentation Impact;
- every reader-facing page changed by implementation;
- relevant architecture and reference pages;
- `docs/src/planned-features.md`;
- `docs/src/features/index.md`;
- `docs/src/SUMMARY.md`.

Create or update:

```text
docs/src/features/<slug>/index.md
```

Use `docs/src/features/_template/index.md`. The record must stand alone; it may link to `design.md` but must not embed
`design.md` or a legacy `tasks.md`. Ensure the design is registered between the feature-design markers in `SUMMARY.md`,
then add the implemented record between the implemented-feature markers in both `SUMMARY.md` and `features/index.md`.

Record delivered behavior, intentional changes, corrected drift, deferred work, documentation paths, commits, and
evidence in the reconciliation bead.

## 3. Validate

Claim the validation step. Classify every required check as `passed`, `failed`, `unavailable`, `waived`, or
`not-applicable`. Build the impacted feature-check set from the design validation strategy, every child
`validation_command`, changed-path ownership, generated/documentation parity, and checks invalidated by later fixes. Run
that set plus `uv run --no-project python scripts/check-docs.py` when documentation changed. Do not automatically run a
whole-repository suite; run one only when the design, repository delivery policy, or explicit user request requires it.
Record exact commands, outcomes, skipped checks, limitations, tested commit, and affected paths. Reuse unchanged focused
task evidence/telemetry, but treat results as valid only for their recorded source boundary. Any later close-review fix
invalidates only affected results, which must be rerun before approval. Do not close validation until required evidence
is complete and current. `unavailable` remains blocking unless the user explicitly waives that exact check. A validation
waiver records the command, reason, affected commit, accepting user decision, and residual risk; it does not waive a
review finding.

## 4. Derive Two Direct Close Assignments, Then Run Both Reviews

Beads is the workflow manifest. Read the feature root, documentation and validation issues, implementation coordinator,
close review issues, implemented record, roadmap/navigation, current findings, and focused-check evidence directly from
Beads and reader-facing files. Do not create a packet, collector, shared context, or second durable assignment manifest.

Pin one immutable Git source boundary from the authoritative feature worktree: `review_boundary_id`, `reviewed_commit`,
`reviewed_diff_base`, `reviewed_diff_digest`, and changed paths. Persist both close states with their owning
`review_issue_id`, source boundary, declared paths/domains/requirement IDs, and `initial_active` before launch. Missing
or stale validation evidence blocks review.

Resolve `implementation-integrity` to `dstack-implementation-reviewer` and `delivery-integrity` to
`dstack-delivery-integrity-reviewer` through `PI-REVIEWER-ROSTER.md`. Missing or unavailable names fail visibly after
optional project-local sync; there is no silent role substitution.

Derive two independent transient assignments from the owning Beads issues, design/docs, focused validation, and the
pinned Git boundary. The implementation assignment declares code and test paths and covers correct code behavior,
quality and simplicity, security, and maintainability. The delivery assignment declares documentation, validation,
Beads, implemented-record, roadmap/navigation, delivery-claim, and drift paths and covers only delivery integrity; it
reconciles former delivery and drift evidence without reviewing code.

Launch exactly two fresh reviewers concurrently. Each receives only its own assignment and a pinned read-only worktree;
each reads assigned evidence directly and reports missing evidence without broadening its scope.

Use executable review state from `../dstack-core/references/REVIEW-STATE.md` and the current-open finding ledger from
`../dstack-core/references/REVIEW-FINDINGS.md` on each owning close review bead. Create the exact required reviewer set
`["implementation-integrity", "delivery-integrity"]` and persist `initial_active` before launch. Each initial report
approves provisionally, records findings/decisions, or becomes incomplete; it never implies final approval. Persist
assignment counts, elapsed/context telemetry when available, and terminal status as operational evidence, not acceptance
evidence.

An initial approval closes through the executable aggregate only when both roles approve and no finding, decision, or
invalidation remains. After fixes, an answered decision, or overlapping reconciliation, rerun only affected impacted
checks and provide one complete aggregate source-boundary reconciliation before invalidating sibling approvals. After
that, resume the same reviewer for the single available verification pass. There is no third pass on the same review
boundary. A material/protected verification finding or post-verification overlap becomes `redesign_required`; do not
launch again against that boundary. Timeout/unavailability preserves partial evidence and permits at most one explicit
same-pass infrastructure replacement, never an automatic retry. A replacement receives the same source boundary, open
findings, resolutions, and post-review diff; if it also fails, stop.

A `redesign_required` stop reports two actionable choices: leave the feature blocked, or authorize one recovery
boundary. Do not continue from reviewer output alone. If the user explicitly authorizes recovery, record their identity,
reason, and affected close-review issue IDs in Beads, then pass
`authorization: {user, decision: authorize, reason, affected_review_issue_ids}` to `review-state.py transition` with
event `redesign`, a new `review_boundary_id`, and all updated reviewed source-boundary fields plus declarations. The
executable state records the prior and new boundaries, consumes the one redesign replacement, and resets the new
boundary to `initial_active`. Recovery without authorization is rejected; do not reuse old approval or infer approval
from historical evidence. Waiver is available only for explicitly non-material findings outside security, correctness,
validation, accessibility, and data-loss-protection, and requires the user's exact accepted scope and rationale.
Protected findings are never waivable at any severity. Close both close reviews only when aggregate `can_close` is true;
then close validation and documentation reconciliation only after their evidence remains current.

## 5. Commit Reconciliation

Run `git status --short`; identify pre-existing or out-of-scope changes and exclude them from the commit. Commit final
code, tests, documentation, and audit-record changes. Include the feature root ID in the commit message. Record the
commit SHA and review outcomes in Beads. Close-out is ready when the delivery step is the next ready item.

## 6. Finalize the close-out interaction boundary

Before asking for or executing the delivery action, finalize every Beads interaction emitted during documentation
reconciliation, validation, and close-out review. Under the repository-scoped `beads-workflow-lock.py` lease, copy only
selected-lineage rows to the feature branch, commit the interaction-only audit commit, and restore the base copy:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py prepare \
  --base-worktree <base-worktree> --feature-worktree <feature-worktree> --root-id <root-id>
git -C <feature-worktree> add .beads/interactions.jsonl
cat > /tmp/dstack-close-interactions-message <<'EOF'
chore(beads): record <slug> close-out state

Beads: <root-id>
EOF
git -C <feature-worktree> commit -F /tmp/dstack-close-interactions-message
uv run <core-dir>/scripts/reconcile-beads-interactions.py finalize \
  --base-worktree <base-worktree> --feature-worktree <feature-worktree> --root-id <root-id>
```

Skip this boundary only when the base interaction export is clean and no close-out Beads mutation emitted a row. If
`prepare` or the inspector reports foreign rows, stop without restoring or closing delivery/root. The base must be clean
before the user chooses `pr`, `merge`, or `ready`; a later delivery action must reacquire the lease and recheck it.

## 7. Choose Delivery Action

When no action was supplied, ask exactly one question:

```text
create PR
merge
leave ready with no delivery action
```

### `ready`

Add `delivery:ready`, record the reconciliation commit, and leave delivery/root open.

### `pr`

Create the pull request with `gh pr create`, record its URL, add `delivery:pr-open`, and leave the root open until merge
is confirmed.

### `merge`

Read the target repository's `AGENTS.md` merge policy. Resolve the worktree that has `<base-branch>` checked out from
`git worktree list --porcelain`; do not assume the current directory is the base worktree. Verify its branch. Require a
clean worktree without stashing, deleting, or including unrelated changes, with one bounded exception: native Beads may
have appended tracked interaction evidence for the selected feature molecule in the base worktree.

Before the first delivery mutation, require the canonical base worktree to be clean. This preflight must run before
closing delivery or the feature root:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py preflight \
  --worktree <base-worktree> --root-id <root-id>
```

If it fails, inspect without mutation and leave delivery/root open:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py inspect \
  --worktree <base-worktree> --root-id <root-id>
```

When the base is dirty only because `.beads/interactions.jsonl` has append-only rows whose `issue_id` is the selected
root ID, its dotted descendant, or separately identified work connected back to that molecule by a local Beads
`discovered-from` or `parent-child` dependency path, preserve those rows on the feature branch before restoring the base
copy. `related` and `blocks` edges alone do not grant this provenance:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py prepare \
  --base-worktree <base-worktree> --feature-worktree <feature-worktree> --root-id <root-id>
git -C <feature-worktree> add .beads/interactions.jsonl
cat > /tmp/dstack-close-interactions-message <<'EOF'
chore(beads): record <slug> close-out state

Beads: <root-id>
EOF
git -C <feature-worktree> commit -F /tmp/dstack-close-interactions-message
uv run <core-dir>/scripts/reconcile-beads-interactions.py finalize \
  --base-worktree <base-worktree> --feature-worktree <feature-worktree> --root-id <root-id>
```

Do not make another pre-merge Beads mutation after `prepare`; if one occurs, rerun `prepare`, amend the interaction-only
commit, and rerun `finalize`. The helper rejects staged changes, non-append edits, malformed or duplicate rows,
unrelated issue IDs, any other dirty path, and restoration before every row is committed byte-for-byte on the feature
branch. If it rejects the state, stop without restoring anything. All other dirty base states remain blocking.

Then require both worktrees to be clean and merge:

```bash
test -z "$(git -C <feature-worktree> status --porcelain)"
test -z "$(git -C <base-worktree> status --porcelain)"
git -C <base-worktree> branch --show-current  # must equal <base-branch>
git -C <base-worktree> merge --ff-only feat/<slug>
git -C <base-worktree> merge-base --is-ancestor feat/<slug> <base-branch>
```

If the base worktree is missing, dirty for another reason, or on another branch, stop before merging. If `--ff-only`
fails, report that the feature must be updated or rebased; never fall back to a merge commit. Only an explicit
repository policy in `AGENTS.md` may replace this default with a merge-commit flow. User selection of `merge` alone does
not authorize a merge commit.

After confirmed merge, capture the actual delivery target but do not close the delivery/root or remove either worktree:

```bash
merge_sha=$(git -C <base-worktree> rev-parse <base-branch>)
```

### Mandatory post-merge finalizer

The merge is not close-out completion until this finalizer passes. In the merged base worktree:

1. Update `docs/src/features/<slug>/index.md` with `Status: delivered` and `Merge commit: <merge_sha>` (annotated as
   fast-forward or merge commit), and record the actual pull request or `not created` value.
2. Reconcile every path listed in the record's `Documentation Updated` section, every reader-facing page changed by the
   feature, `docs/src/planned-features.md`, `docs/src/features/index.md`, and `docs/src/SUMMARY.md`. Remove stale claims
   that the merge or delivery is pending; do not ask a delivery-integrity reviewer to discover this mechanically
   detectable drift.
3. Run the semantic delivery verifier against the record and every reconciled reader-facing path:

```bash
uv run <core-dir>/scripts/verify-delivery-state.py \
  --base-worktree <base-worktree> --base-branch <base-branch> \
  --record docs/src/features/<slug>/index.md --merge-sha <merge_sha> \
  --path <reader-facing-path> --path <another-reader-facing-path>
```

The verifier must confirm that the recorded merge SHA is an ancestor of the base branch, the record says delivered and
contains that SHA, and no supplied path contains a stale pending/unmerged delivery claim. Then rerun
`uv run --no-project python scripts/check-docs.py` and every formatter, linter, build, test, and feature-specific check
affected by the finalizer. Never reuse pre-merge validation for these edits.

Stage only the finalizer paths, commit them on the merged base branch, and record both SHAs in Beads:

```bash
git -C <base-worktree> add docs/src/features/<slug>/index.md <reader-facing-paths> \
  docs/src/planned-features.md docs/src/features/index.md docs/src/SUMMARY.md
cat > /tmp/dstack-post-merge-finalizer-message <<'EOF'
docs(<scope>): reconcile <slug> delivery state

Beads: <root-id>
EOF
git -C <base-worktree> commit -F /tmp/dstack-post-merge-finalizer-message
finalizer_sha=$(git -C <base-worktree> rev-parse HEAD)
# The guarded delivery finalizer records both SHAs in the Beads close reason.
```

If the verifier, documentation check, finalizer commit, or guarded Beads closure fails, report
`blocked by post-merge reconciliation` and preserve both worktrees. Do not close delivery/root or claim completion.

Only after the finalizer passes, use the guarded delivery finalizer to close delivery and the feature root. It rechecks
the merge/finalizer evidence and the clean base boundary under the repository-scoped lease. Do not close delivery/root
with direct `bd close` commands. The guard records
`Post-merge delivery SHA: <merge-sha>; finalizer commit: <finalizer-sha>` in the Beads close reason:

```bash
uv run <core-dir>/scripts/finalize-feature-delivery.py \
  --base-worktree <base-worktree> --base-branch <base-branch> \
  --record docs/src/features/<slug>/index.md --merge-sha <merge-sha> \
  --finalizer-sha <finalizer-sha> \
  --path <reader-facing-path> --path <another-reader-facing-path> \
  --delivery-id <delivery-id> --root-id <root-id>
```

These final Beads mutations may append new selected-feature interaction rows in the now-merged base worktree. Verify and
commit only that evidence:

```bash
uv run <core-dir>/scripts/reconcile-beads-interactions.py verify-post-merge \
  --base-worktree <base-worktree> --root-id <root-id>
git -C <base-worktree> add .beads/interactions.jsonl
cat > /tmp/dstack-delivery-interactions-message <<'EOF'
chore(beads): record <slug> delivery

Beads: <root-id>
EOF
git -C <base-worktree> commit -F /tmp/dstack-delivery-interactions-message
```

Skip this post-merge commit when the worktree remains clean. Rerun the verifier after any interaction commit and before
cleanup. Any rejection or additional dirty path blocks cleanup and must be preserved for explicit reconciliation. Verify
navigation and the implemented record, then remove the feature worktree. If `dstack.activeFeature` still equals this
feature, clear that repository-local setting after confirmed delivery. Never push or delete a remote branch unless
separately authorized.

Return one readiness state: `ready for delivery`, `ready after reconciliation fixes`,
`blocked by implementation/docs mismatch`, or `blocked by incomplete validation`, together with the canonical feature
reference and human name, root ID, docs, evidence, reviews, commit, action, and Beads changes.
