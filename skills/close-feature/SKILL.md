---
name: close-feature
description: Finalize a completed Beads feature by reconciling documentation, validating delivery, recording implementation, reviewing drift, and executing `pr`, `merge`, or `ready`. Use when asked to close a feature, prepare it for delivery, or reconcile implementation and documentation after its implementation coordinator closes.
metadata:
  version: "0.0.0"
allowed-tools: Read Glob Grep Edit Write Bash Task AskUserQuestion
---

# Purpose

Use this skill after the lifecycle implementation coordinator closes. It converts delivered code into reconciled,
validated, auditable product state.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

Delivery authority:

- Invocation authorizes local reconciliation, validation, workflow commits, and Beads updates for the selected feature.
- Only explicit `pr` mode authorizes pull-request creation. Only explicit `merge` mode authorizes merge and post-merge
  worktree removal. `ready` and no-action mode authorize neither.
- The workflow never force-pushes, deletes a remote branch, bypasses hooks, or removes a worktree before a confirmed
  merge.
- Holistic-review subagents are read-only.

## Supported Actions

- `pr`: create a pull request after successful close-out.
- `merge`: merge after successful close-out and finalize the feature.
- `ready`: leave the feature ready without PR or merge.
- no action: complete close-out, then ask the user to choose `pr`, `merge`, or `ready`.

## Execution

## 1. Activate and Inspect

Run:

```bash
bd prime
bd show <feature-root> --json
```

Resolve `docs_reconcile_id`, `validation_id`, `review_delivery_id`, `review_drift_id`, and `delivery_id` from root
metadata. Query the full molecule or child list only to repair missing metadata. Activate and verify
`feat/<num>-<slug>`. Inspect commits, implementation, tests, and changed files before deciding whether documentation is
accurate.

Continue only after all lifecycle IDs resolve, the active worktree is `feat/<num>-<slug>`, the implementation
coordinator is closed, and no open `migration:reconciliation` task blocks close-out.

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
docs/src/features/<num>-<slug>/index.md
```

Use `docs/src/features/_template/index.md`. The record must stand alone; it may link to `design.md` but must not embed
`design.md` or a legacy `tasks.md`. Add it between the implemented-feature markers in both `SUMMARY.md` and
`features/index.md`.

Record delivered behavior, intentional changes, corrected drift, deferred work, documentation paths, commits, and
evidence in the reconciliation bead.

## 3. Validate

Claim the validation step. Classify every required check as `passed`, `failed`, `unavailable`, `waived`, or
`not-applicable`. Run `uv run scripts/check-docs.py`, repository-wide checks, and every feature-specific command named
by the design or implementation beads. Record commands, outcomes, skipped checks, and limitations. Treat these results
as valid only for the exact files and commit tested; any later holistic-review fix invalidates the affected results. Do
not close validation until required evidence is complete and current. `unavailable` remains blocking unless the user
explicitly waives that exact check. A waiver must record the command, reason, affected commit, accepting user decision,
and residual risk.

## 4. Run Two Holistic Reviews

Launch two isolated subagents.

### Delivery Reviewer

Review correctness, failure behavior, security-sensitive changes, maintainability, test quality, and delivered-scope
compliance.

### Drift Reviewer

Compare implementation, design, reader-facing docs, architecture decisions, reference contracts, implemented-feature
record, roadmap, and Beads history. Distinguish intentional evolution from accidental drift.

Claim the matching review task and record each finding and resolution. Resolve actionable findings. After the final
review fix, rerun every affected formatter, linter, build, test, feature-specific command, and
`uv run scripts/check-docs.py`. Update the validation bead with the post-fix commands and outcomes; do not reuse pre-fix
results. Close each review and the validation step only when no actionable finding remains and validation reflects the
final worktree state.

## 5. Commit Reconciliation

Run `git status --short`; identify pre-existing or out-of-scope changes and exclude them from the commit. Commit final
code, tests, documentation, and audit-record changes. Include the feature root ID in the commit message. Record the
commit SHA and review outcomes in Beads. Close-out is ready when the delivery step is the next ready item.

## 6. Choose Delivery Action

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

Merge through the repository-approved worktree flow. After success, record the merge commit, close delivery, close the
feature root, verify navigation and the implemented record, and remove the worktree.

Return one readiness state: `ready for delivery`, `ready after reconciliation fixes`,
`blocked by implementation/docs mismatch`, or `blocked by incomplete validation`, together with docs, evidence, reviews,
commit, action, and Beads changes.
