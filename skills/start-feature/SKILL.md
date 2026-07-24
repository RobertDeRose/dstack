---
name: start-feature
description: Activate and review a planned Beads feature, create or switch its worktree, reconcile its design and execution graph, and mark it ready for implementation. Use when asked to start or prepare a planned feature.
metadata:
  version: "0.5.6"
allowed-tools: Read Glob Grep Edit Write Bash Task AskUserQuestion
---

# Purpose

Use this skill for any planned feature epic. The user may identify it by canonical `<slug>`, exact feature name, unique
name fragment, or Beads ID. It owns bounded promotion of roadmap-only migrated roots, specification review, worktree
activation, and implementation-readiness reconciliation. Resolve `<core-dir>` as the installed `../dstack-core` skill
directory.

## Execution

## 1. Resolve Feature Context

Run `bd prime`, then resolve a human selector through Beads. With a supplied selector:

```bash
uv run <core-dir>/scripts/resolve-feature.py "<feature-selector>" --json
```

When the user invokes `/start-feature` without a selector, select the next ready feature epic instead of asking for or
copying an opaque ID:

```bash
uv run <core-dir>/scripts/resolve-feature.py --next --json
```

Use the returned `id` for Beads mutations and `feature_reference` for branches, paths, messages, and subsequent workflow
commands:

```bash
bd show <resolved-root-id> --json
```

The selected issue must be an epic carrying `workflow:feature`. Read root metadata first. It should provide feature
slug, human name, paths, base branch, implementation repository/path, workflow kind, and lifecycle IDs. Stop on an
ambiguous selector and show the resolver's human-readable candidates; do not guess or append characters to an ID.

When the selected root is roadmap-only and lacks `design.md` or lifecycle metadata, do not stop or ask the user to
invoke another skill. Run the bounded single-feature planning phase from `/plan-features`: resolve only the missing
outcome, boundaries, dependencies, validation, documentation impact, and repository ownership; create the design,
lifecycle, and bounded implementation children; then continue this workflow. Preserve the existing feature slug and root
ID. Query only the specific review or reconciliation beads needed for this invocation.

When lifecycle IDs are missing, repair metadata once: use `bd mol show <feature-root> --json` for a molecule, or
`bd list --parent <feature-root> --all --json` for a migrated parent-child lifecycle. Resolve children by structured
metadata and labels rather than title text, then persist their IDs on the root.

Read `design.md`, exact pages named in its Documentation Impact section, relevant architecture pages, current
implementation evidence, and relevant implemented-feature records.

## 2. Resolve the Implementation Repository

Use `implementation_path` when present. Verify it is a Git root and that it matches `implementation_repository`. Never
create a worktree in the planning repository for a feature owned by another repository. When metadata is missing and
repository ownership is ambiguous, ask one blocking question and persist the answer on the root.

## 3. Activate the Worktree

Use:

```text
feat/<slug>
```

When `wt` is available, use it and treat JSON stdout as authoritative:

```bash
# Create when the feature branch/worktree does not exist.
wt switch --create --yes --format json feat/<slug> --base <base-branch>

# Switch when the worktree already exists.
wt switch --format json feat/<slug>
```

When `wt` is unavailable, use native Git and handle all three states explicitly:

```bash
# Inspect existing worktrees and branches.
git worktree list --porcelain
git show-ref --verify --quiet refs/heads/feat/<slug>

# Branch and worktree both absent:
git worktree add -b feat/<slug> <worktree-path> <base-branch>

# Branch exists but has no worktree:
git worktree add <worktree-path> feat/<slug>

# Worktree already exists:
# Use the path reported by `git worktree list --porcelain`; do not add another one.
```

Run subsequent Git and file operations from the resolved worktree path, or with `git -C <worktree-path>`. Verify both:

```bash
git -C <worktree-path> branch --show-current
git -C <worktree-path> rev-parse --show-toplevel
```

The branch must equal `feat/<slug>` and the root must equal the resolved worktree path before editing. Claim the feature
root when appropriate:

```bash
bd update <feature-root> --claim
```

## 4. Build Context Once, Then Run Four Reviews

Launch exactly one fresh, read-only context builder before any reviewer. Store its packet in the subagent run's
ephemeral artifact directory, never in the repository. The packet must contain factual evidence only: feature authority
and identity, reviewed requirements, relevant architecture and prior decisions, changed/current source paths, Beads
graph and acceptance criteria, documentation impact, validation evidence, and exact source locations. It must not
contain findings, recommendations, or a verdict.

Launch exactly four role reviewers with `context: fresh`, giving each the same packet and its distinct goal below. Each
reviewer independently reasons from the packet, verifies evidence critical to its role, and reads additional source only
when needed. Claim the matching lifecycle task before recording each review. Do not add general-purpose or confidence
reviewers unless a distinct uncovered risk or the user explicitly requires one.

### Architecture Consistency

Compare the design with documented boundaries, invariants, ownership, established patterns, prior decisions, current
code, and relevant completed features. Identify conflicting assumptions, missing reuse, and undocumented architecture
changes.

### Simplicity and Maintainability

Challenge accidental complexity, speculative abstractions, hidden coupling, unclear ownership, weak failure handling,
and avoidable operational burden. Prefer the smallest correct design.

### Documentation Readiness

Verify that every reader-facing change names an exact existing or new page, each page has a clear reader purpose, new
pages are placed in `SUMMARY.md`, and product documentation stands alone without the internal feature design.

### Execution Readiness

Review implementation children, blocker direction, parallel safety, acceptance criteria, validation, documentation
ownership, and commit boundaries. Confirm every remaining task depends on `spec-reconcile` and is small enough for one
agent without inventing design intent.

Record findings and resolutions:

```bash
bd update <review-task-id> --claim
bd update <review-task-id> --append-notes "<findings and resolution>"
```

Review is complete when all four review beads contain independently produced evidence, findings, and dispositions. If
reconciliation changes a reviewed domain, resume only its original reviewer. Refresh the shared packet only after broad
design, architecture, task-graph, or documentation-structure changes. Launch a fresh replacement only when the original
cannot be resumed or the fix materially changes that role's scope; provide the original packet, finding, resolution, and
post-review diff.

## 5. Reconcile the Specification

Apply clear fixes to `design.md`, Beads descriptions, acceptance criteria, dependencies, metadata, validation, and
documentation impact. Ask one blocking design question at a time when user policy or intent is genuinely ambiguous.

For migrated features, resolve any `migration:reconciliation` bead that blocks specification or close-out. Preserve
legacy evidence in notes while making the current design and Beads graph authoritative.

Commit the reviewed design and graph boundary. Include the feature root ID in the commit message. Record the commit SHA
in the `spec-reconcile` task.

Close review tasks only after their findings are resolved, then close `spec-reconcile`:

```bash
bd close <review-task-id> --reason "Review complete; findings reconciled"
bd close <spec-reconcile-id> --reason "Reviewed design and execution graph committed at <sha>"
```

## 6. Confirm Implementation Readiness

Run:

```bash
bd ready --parent <implementation-id> --json
```

At least one implementation child should now be ready unless the design intentionally contains only a gate or deferred
work. Persist the successfully prepared feature as this repository's implementation default:

```bash
git -C <worktree-path> config dstack.activeFeature <slug>
```

Set this only after specification reconciliation and implementation-readiness checks pass. The value is repository-local
Git state, so a later `/implement-feature` invocation can resume the feature even when invoked from the base worktree.

Return the canonical feature reference and human name first, followed by the root ID for auditability, worktree,
reviewed-design commit, review findings, decisions made, remaining blockers, and next ready implementation task. Any
recommended continuation must use `/implement-feature <slug>` rather than only the Beads hash.
