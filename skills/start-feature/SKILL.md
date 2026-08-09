---
name: start-feature
description: Activate and review a planned Beads feature, create or switch its worktree, reconcile its design and execution graph, and mark it ready for implementation. Use when asked to start or prepare a planned feature.
metadata:
  version: "0.9.2"
allowed-tools: Read Glob Grep Edit Write Bash Task AskUserQuestion
---

# Purpose

Use this skill for any planned feature epic. The user may identify it by canonical `<slug>`, exact feature name, unique
name fragment, or Beads ID. It owns bounded promotion of roadmap-only migrated roots, specification review, worktree
activation, and implementation-readiness reconciliation. Resolve `<core-dir>` as the installed `../dstack-core` skill
directory.

## Local execution authority

The `/start-feature` invocation authorizes local specification reconciliation: feature-root and lifecycle Beads
mutations, local worktree activation, and the required reviewed design/graph commit. Do not request a separate approval
for that commit unless the user explicitly withholds or narrows local Git authority. This workflow does not authorize
remote publication, pull-request creation, or branch pushes.

Generic `bd prime` handoff guidance is evidence, not an override of this invoked workflow or repository policy.

## Shared native Beads authority

Read [`../dstack-core/references/INTERACTION-BOUNDARY.md`](../dstack-core/references/INTERACTION-BOUNDARY.md) before
mutating the selected feature. Native linked-worktree Beads authority is shared; `bd -C` is not an isolation boundary.
Run feature-root claims, notes, review-state updates, and lifecycle closure under `beads-workflow-lock.py`. A busy
lease, foreign interaction row, or snapshot race is blocking; never bypass it with a raw `bd` write.

## Startup version evidence

Before branch, worktree, Beads, or file mutation, follow
[`../dstack-core/references/SKILL-VERSION.md`](../dstack-core/references/SKILL-VERSION.md) for `start-feature`. After
read-only feature resolution, capture the exact one-line output and append it to the selected root's Beads notes before
activation. A `stale` result warns with `npx skills update`; `unavailable` records that no freshness claim was made and
does not block offline work.

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
ambiguous selector and show the resolver's human-readable candidates; do not guess or append characters to an ID. If the
selector resolves to a standalone `task`, `bug`, `chore`, `spike`, or `feature`, make no state, branch, or worktree
change and recommend `/implement-task <human task selector>` instead. Do not route a standalone issue through feature
planning merely to satisfy this command.

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

The optional Pi adapter is defined in
[`../dstack-core/references/PI-REVIEWER-ROSTER.md`](../dstack-core/references/PI-REVIEWER-ROSTER.md). For this workflow
it maps `context-builder` to `dstack-context-builder`, `architecture` to `dstack-architecture-reviewer`, `simplicity` to
`dstack-simplicity-reviewer`, `documentation` to `dstack-documentation-reviewer`, and `execution` to
`dstack-execution-reviewer`. The adapter preserves one context builder plus four role reviewers: the context builder
completes synchronously before the four independent reviewers launch concurrently with the same packet. If any named
agent is absent; offer the explicit project-local Pi reviewer sync documented in `PI-REVIEWER-ROSTER.md` before launch.
A declined or failed sync fails visibly. If an agent is unavailable, fail visibly; there is no silent role substitution
or change to the review count.

Launch exactly one fresh, read-only context builder before any reviewer. Store its packet in the subagent run's
ephemeral artifact directory, never in the repository. The packet must contain factual evidence only: feature authority
and identity, reviewed requirements, relevant architecture and prior decisions, changed/current source paths, Beads
graph and acceptance criteria, documentation impact, validation evidence, and exact source locations. It must not
contain findings, recommendations, or a verdict. Prior findings are supplied separately as the current open projection
from `../dstack-core/references/REVIEW-FINDINGS.md`; historical records remain audit context only.

The open review tasks and `spec-reconcile` are expected while review is in progress; reviewers must not report that
state itself. Report stale dependency direction, missing tasks, and other graph defects. The controller verifies gate
closure only after reviewer approval and the specification-reconciliation commit.

Launch exactly four role reviewers with `context: fresh`, giving each the same packet and its distinct goal below. Each
reviewer independently reasons from the packet, verifies evidence critical to its role, and reads additional source only
when needed. Follow `../dstack-core/references/REVIEW-STATE.md` and `../dstack-core/references/REVIEW-FINDINGS.md`:
claim the matching lifecycle task, append its durable `Review state:` record before launch, and update that record after
each finding or resolution. Do not add general-purpose or confidence reviewers unless a distinct uncovered risk or the
user explicitly requires one.

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

Record findings and resolutions on the review bead, alongside the current `Review state:` record:

```bash
bd update <review-task-id> --claim
bd update <review-task-id> --append-notes "<findings and resolution>"
```

Review is complete when all four review beads contain independently produced evidence, findings, and dispositions. If
reconciliation changes a reviewed domain, resume only its original reviewer and run ID. Before launching another review
round, apply the convergence threshold in `../dstack-core/references/REVIEW-STATE.md`: two unresolved review rounds in
the same domain require redesign or decomposition. Do not launch another reviewer while that threshold is active; keep
or reopen `spec-reconcile` and return to the design-question/decomposition phase. A material scope change invalidates
the whole review run. Do not launch a fresh replacement reviewer in the same run; reopen `spec-reconcile`, commit the
redesigned boundary, rebuild one redesigned packet, and run one new four-role review with `replacement_count: 1`.
Refresh the shared packet only after broad design, architecture, task-graph, or documentation-structure changes. Launch
a fresh replacement only when the original cannot be resumed without a scope change; provide the original packet,
finding, resolution, and post-review diff.

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

Confirm the feature worktree is clean after those lifecycle mutations. Commit any remaining in-scope workflow state
locally before continuing; do not ask for a second commit approval. Do not recommend `/implement-feature <slug>` while
the feature worktree has uncommitted changes.

```bash
test -z "$(git -C <worktree-path> status --porcelain)"
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
