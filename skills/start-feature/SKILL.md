---
name: start-feature
description: Activate and review a planned Beads feature, create or switch its worktree, reconcile its design and execution graph, and mark it ready for implementation. Use when asked to start or prepare a planned feature.
metadata:
  version: "0.0.0"
allowed-tools: Read Glob Grep Edit Write Bash Task AskUserQuestion
---

# Purpose

Use this skill for any planned feature root. It owns bounded promotion of roadmap-only migrated roots, specification
review, worktree activation, and implementation-readiness reconciliation.

## Execution

## 1. Resolve Feature Context

Run:

```bash
bd prime
bd show <feature-root> --json
```

Read root metadata first. It should provide feature identity, paths, base branch, implementation repository/path,
workflow kind, and lifecycle IDs.

When the selected root is roadmap-only and lacks `design.md` or lifecycle metadata, do not stop or ask the user to
invoke another skill. Run the bounded single-feature planning phase from `/plan-features`: resolve only the missing
outcome, boundaries, dependencies, validation, documentation impact, and repository ownership; create the design,
lifecycle, and bounded implementation children; then continue this workflow. Preserve the existing feature number and
root ID. Query only the specific review or reconciliation beads needed for this invocation.

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
feat/<num>-<slug>
```

When `wt` is available, use it and treat JSON stdout as authoritative:

```bash
# Create when the feature branch/worktree does not exist.
wt switch --create --yes --format json feat/<num>-<slug> --base <base-branch>

# Switch when the worktree already exists.
wt switch --format json feat/<num>-<slug>
```

When `wt` is unavailable, use native Git and handle all three states explicitly:

```bash
# Inspect existing worktrees and branches.
git worktree list --porcelain
git show-ref --verify --quiet refs/heads/feat/<num>-<slug>

# Branch and worktree both absent:
git worktree add -b feat/<num>-<slug> <worktree-path> <base-branch>

# Branch exists but has no worktree:
git worktree add <worktree-path> feat/<num>-<slug>

# Worktree already exists:
# Use the path reported by `git worktree list --porcelain`; do not add another one.
```

Run subsequent Git and file operations from the resolved worktree path, or with `git -C <worktree-path>`. Verify both:

```bash
git -C <worktree-path> branch --show-current
git -C <worktree-path> rev-parse --show-toplevel
```

The branch must equal `feat/<num>-<slug>` and the root must equal the resolved worktree path before editing. Claim the
feature root when appropriate:

```bash
bd update <feature-root> --claim
```

## 4. Run Four Isolated Reviews

Launch isolated subagents with distinct goals. Claim the matching lifecycle task before recording each review.

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

Review is complete when all four review beads contain independently produced evidence, findings, and dispositions.

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
work. Return the root ID, worktree, reviewed-design commit, review findings, decisions made, remaining blockers, and the
next ready implementation task.
