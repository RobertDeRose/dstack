---
name: start-feature
description: Activate and review a planned Beads feature, create or switch its worktree, reconcile its design and execution graph, and mark it ready for implementation. Use when asked to start or prepare a planned feature.
metadata:
  version: "0.11.2"
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
does not block offline work. Establish `workflow_run_id` before this diagnostic, using the harness value or one created
once for this session. If installed skills are refreshed, stop this session; continue only from a new session that
records an explicit rebind.

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

When the selected root is roadmap-only and lacks `design.md` or lifecycle metadata, use this canonical promotion path;
do not stop, create a duplicate root, or ask the user to invoke another skill. Run the bounded single-feature planning
phase from `/plan-features`: resolve only the missing outcome, boundaries, dependencies, validation, documentation
impact, and repository ownership, and create the design. Write a `dstack.legacy-feature-promotion.v1` JSON plan
containing the feature identity/repository fields and at least one bounded implementation task. Every task provides
`task_key`, title, description, acceptance criteria, owner, validation commands, commit boundary, optional
labels/priority, and `needs` task keys. Under the repository lease, run:

```bash
uv run <core-dir>/scripts/promote-legacy-feature.py \
  --repository-root <primary-worktree> \
  --root-id <existing-feature-root> \
  --formula <primary-worktree>/.beads/formulas/dstack-feature.formula.toml \
  --plan <promotion-plan.json> \
  --output <promotion-result.json>
```

The helper attaches formula-defined lifecycle children and planned implementation tasks directly to the existing root,
wires dependencies, persists complete identity/lifecycle metadata, and is digest-bound and idempotent. It never pours or
creates a replacement root. Preserve the existing feature slug and root ID. The later topology guard remains the sole
owner for upgrading formula review topology before assignments. Query only the specific review or reconciliation beads
needed for this invocation.

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

The branch must equal `feat/<slug>` and the root must equal the resolved worktree path before editing. Before any claim,
note, or other mutation, guard the selected feature's read-only resolved root against an unapplied or newer topology:

```bash
python3 <core-dir>/scripts/migrate-review-topology.py \
  --repository-root <primary-worktree> guard \
  --root-id <feature-root> --controller-topology-version 3
```

If old review kinds remain without a cutover marker, plan and apply migration from the canonical primary worktree before
continuing. The migrator is the sole topology mutation owner and acquires the repository lease itself. Never emulate its
writes from this skill. Only after a successful guard may the workflow claim the feature root under the ordinary lease.

## 4. Derive Direct Assignments, Then Run Two Reviews

Beads is the workflow manifest. Read the selected feature root, design/specification issues, implementation coordinator
and children, current validation/documentation ownership, and exact review issues from Beads. Do not create a shared
evidence bundle, collector, shared context, or second durable manifest.

Pin one immutable Git source boundary from the authoritative feature worktree before launch: `review_boundary_id`,
`reviewed_commit`, `reviewed_diff_base`, `reviewed_diff_digest`, and changed paths. Before creating the readiness
assignment, generate its transient embedded-Dolt-safe graph with `build-beads-review-projection.py`, including the exact
source boundary and allowed paths. Immediately run the helper's `--verify` mode against current Beads authority. Missing
root/coordinator/task fields, incomplete edges, a digest mismatch, or a stale projection fails closed before reviewer
launch. Pass this projection directly to execution readiness; reviewers never need `.beads` filesystem access. It is
role-specific transient evidence, not a packet, collector, or second durable manifest.

Persist each review state's owning `review_issue_id`, source boundary, declared paths, domains, requirement IDs, and
`initial_active` state before launching its reviewer. Append every state and finding with `append-review-note.py` under
the repository lease, passing the exact one-line JSON on standard input. The helper validates the schema and sends the
unchanged JSON bytes to Beads without nested shell quoting. The pinned read-only worktree is the source for reviewer
inspection.

The assignment includes the pinned read-only worktree and its exact source boundary. Derive one transient assignment per
role from the current Beads issue and design/docs. It contains the owning Beads issue/title, description, acceptance
criteria, dependencies, validation/documentation ownership, source-boundary fields, declared paths/domains/requirements,
explicit non-goals, and the structured report contract. The clarity assignment also identifies the design's explicit
`current_state_gaps` and `implementation_boundary`; a current mismatch is an expected implementation gap when the design
defines its replacement, owner, acceptance, migration/cutover, compatibility, and failure behavior. Resolve the exact Pi
names in `../dstack-core/references/PI-REVIEWER-ROSTER.md`: logical `specification-clarity` maps to
`dstack-clarity-reviewer`, and `execution-readiness` maps to `dstack-readiness-reviewer`. Missing or unavailable names
fail visibly after optional project-local sync; there is no silent substitution.

Launch exactly two independent fresh reviewers concurrently. Give each only its transient role assignment and a pinned
read-only worktree. Reviewers gather assigned evidence directly, report missing evidence, and never broaden the
assignment silently.

### Specification Clarity

Review behavior, boundaries, compatibility, ownership, failure/recovery policy, documentation intent, and unresolved
user decisions. Do not invent policy. Do not block merely because implementation or a forward migration does not exist
yet when the design explicitly owns that current-state gap; block only ambiguous or missing replacement boundaries.

### Execution Readiness

Review task scope, dependency direction, ownership, validation, documentation ownership, acceptance criteria, and commit
boundaries. Work must be executable without inventing intent.

Follow `../dstack-core/references/REVIEW-STATE.md` and `REVIEW-FINDINGS.md`. Claim each matching lifecycle review bead
and append its current executable state before launch. Review state is per reviewer; aggregate state uses exactly
`specification-clarity` and `execution-readiness`. Open review tasks and `spec-reconcile` are expected and are not
findings. Do not add confidence reviewers. Resume only affected original reviewers. A material scope change returns to
redesign; timeout/unavailability and finite replacement behavior follow the state helper. After a terminal
`redesign_required` state, reconcile and commit a new boundary, then use the helper's one bounded `redesign` transition
with a new boundary ID; never launch another reviewer against the old boundary.

## 5. Reconcile the Specification

Apply clear fixes to `design.md`, Beads descriptions, acceptance criteria, dependencies, metadata, validation, and
documentation impact. Use `../dstack-core/scripts/review-state.py` for reviewer transitions and aggregate state.
`spec-reconcile` cannot close while any reviewer or aggregate state contains `decision_required`, `changes_required`, an
incomplete review, `waiver_required`, or `redesign_required`.

When a reviewer identifies genuinely unresolved user policy or intent, preserve its decision record and stop. Present
one decision brief with these labeled elements:

- **Issue:** what is undecidable and the evidence or explicit uncertainty that prevents a safe inference;
- **Affected requirements/tasks:** every recorded requirement and task ID;
- **Recommendation:** one choice and why it best preserves the reviewed boundaries;
- **Alternatives and consequences:** each viable alternative with its concrete trade-off; and
- **Question:** exactly one precise question that can resolve the recorded decision.

Do not hide issue detail behind the question, ask multiple questions, or invent an answer. After the user responds,
append the answer's `author`, exact `value`, and the current `reviewed_diff_digest` as `boundary_digest` to the durable
decision record before invoking `review-state.py transition` with event `reconcile`. The helper validates that digest
against the current source boundary and preserves resolved decision evidence. Persist the returned state as the next
append-only `Review state:` record before verification. The helper's result is authoritative. The transition must
resolve every compound pending condition and exact finding ID together; it consumes the only verification pass.

After reconciliation, invoke `review-state.py aggregate` with every required reviewer state and the complete changed
path, domain, and requirement-ID sets. Supply one complete `reconciliation_boundary` when the Git source boundary
changed; no transient assignment identity is persisted. The aggregate applies the common boundary atomically before
sibling approval invalidation. Persist every reviewer state returned by the aggregate, including sibling approval
invalidations, before resuming affected original reviewers. Repeat aggregate state after verification and close
review/specification gates only when its returned `can_close` is exactly `true`. Missing reviewers, unresolved compound
conditions, incomplete/waiver/redesign state, or an overlapping post-verification change blocks closure.

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
