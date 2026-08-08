# Feature lifecycle

## Responsibilities

```text
Beads                                            executable state and dependencies
docs/src/features/<slug>/design.md         intended feature behavior and design
reader-facing docs under docs/src/               current supported behavior
code and tests                                   implementation evidence
docs/src/features/<slug>/index.md          delivered reconciliation and audit record
```

Workflow commands are installed from `RobertDeRose/dstack` with the `skills` CLI. The CLI manages the agent-specific
installation paths and updates; Copier manages this repository scaffold.

## Start a session

```bash
bd prime
bd ready --type epic --label workflow:feature --json --limit 0
bd ready --json
```

## Executing skill version

Each workflow records the installed skill's frontmatter `metadata.version` before its first mutation. When a local
canonical dstack checkout is available, startup compares that version and records the exact `Skill version evidence:`
line. A stale installed skill warns with `npx skills update`; unavailable canonical evidence reports that no freshness
claim was made and does not block offline work. The installed skill remains execution authority.

## Plan

`/plan-features` asks design-changing questions, defines the documentation architecture, creates slug-named feature
designs, pours one Beads epic/molecule per feature, and decomposes lifecycle and implementation into bounded child
tasks. Native planning resolves every decision needed by those tasks before implementation; unresolved decision gaps may
remain only on imported migration work with explicit reconciliation blockers. It recommends the next feature by
canonical slug and human name rather than by an opaque Beads hash.

A new feature uses:

```text
docs/src/features/feature-slug/design.md
feat/feature-slug
```

## Review and start

`/start-feature <slug>` resolves the human feature reference through Beads, activates the worktree, and runs four
isolated reviews. An exact feature name or a unique name fragment also resolves; the Beads ID remains internal
mutation/audit evidence.

The feature root is an epic. Lifecycle tasks are direct children, and bounded implementation tasks sit beneath the
implementation coordinator task. A milestone is not used as the feature container.

One fresh, read-only context builder gathers a factual evidence packet once. Four fresh reviewers share that packet and
independently cover:

1. architecture consistency;
2. simplicity and maintainability;
3. documentation readiness;
4. execution-graph readiness.

### Optional Pi reviewer adapter

The dstack review contract is tool-agnostic. A Pi-based controller may opt into the exact roster in
`skills/dstack-core/references/PI-REVIEWER-ROSTER.md` without installing or mutating user Pi configuration. If required
names are missing, offer the explicit project-local sync documented by that reference; the adapter itself remains
non-mutating:

| Logical role      | Pi agent definition             |
|-------------------|---------------------------------|
| `context-builder` | `dstack-context-builder`        |
| `architecture`    | `dstack-architecture-reviewer`  |
| `simplicity`      | `dstack-simplicity-reviewer`    |
| `documentation`   | `dstack-documentation-reviewer` |
| `execution`       | `dstack-execution-reviewer`     |
| `task`            | `dstack-task-reviewer`          |
| `delivery`        | `dstack-delivery-reviewer`      |
| `drift`           | `dstack-drift-reviewer`         |

The adapter preserves the workflow counts: context packets are built synchronously, then independent role reviewers
launch concurrently with the same packet. A declined or failed sync, or an unavailable named agent, fails visibly; there
is no silent role substitution. Beads review beads or standalone task notes remain the authoritative
`Review state:`/`Finding:` owner.

The packet contains factual source locations but no findings, recommendations, or verdict. Reviewers read extra source
when it is insufficient. Feature workflows persist the durable `Review state:` record from the installed dstack-core
`REVIEW-STATE.md` reference on their review beads. A standalone workflow has no separate review bead: its selected task
notes are the authoritative review ledger for `Review state:` and `Finding:` records, including reviewer session, packet
identity/digest, reviewed commit/diff boundary, and disposition. Supply reviewers the current open projection from
`REVIEW-FINDINGS.md`; retain historical findings for audit. Do not add confidence reviewers without a distinct uncovered
risk or user request. Fix verification resumes only affected reviewers and their run IDs; fresh replacements are used
only when an original is unavailable. A material scope change invalidates the whole review run; reopen specification
reconciliation, commit the redesigned boundary, and run one new bounded review with a new packet. Refresh a shared
packet only after broad design, architecture, task-graph, or documentation-structure changes. Two unresolved review
rounds in the same domain are a convergence stop: record `redesign_required`, do not launch another reviewer, and return
through specification redesign or decomposition before creating a new packet.

Open review tasks and `spec-reconcile` are expected during review and are not findings by themselves. Reviewers report
stale dependency direction, missing tasks, and other graph defects; the controller verifies gate closure only after
approval and the specification-reconciliation commit.

Invoking `/start-feature` authorizes its local reconciliation work, including the reviewed design/graph commit and
feature-scoped Beads mutations. It does not authorize remote publication, pull-request creation, or branch pushes. It
reconciles clear findings, asks only blocking design questions, commits the reviewed design, and closes `spec-reconcile`
only when implementation can proceed without inventing intent. Before recommending implementation, it commits any
remaining in-scope workflow state and confirms the feature worktree is clean. A successful start records the canonical
feature in repository-local Git configuration so `/implement-feature` can resume it from the base worktree when no
selector is supplied.

## Implement

Claim the next ready task beneath the implementation coordinator:

```bash
bd ready --parent <implementation-id> --claim --json
bd show <task-id> --json
```

Before mutating code, run a semantic boundedness check: one independently reviewable behavior, one primary owner, and
one practical commit boundary. Character counts are warning signals only. Cross-boundary work returns to specification
reconciliation without code changes.

Material changes to behavior, ownership, compatibility, or acceptance stop implementation and invalidate the reviewed
source boundary. Reopen specification reconciliation and affected review gates, mark stale review evidence invalid,
reconcile and commit the new specification boundary, and complete its review before reclaiming implementation. An
editorial clarification may stay in place only when it does not alter reviewed intent, ownership, compatibility,
acceptance, or the review boundary.

After each child closes, the implementation loop runs a cohesion checkpoint against new evidence. New ownership
boundaries, migrations, external dependencies, or risky effect classes require inspection, but incidental complexity
alone does not require decomposition. If remaining outcomes are independently valuable and reviewable, pause the
coordinator and return through normal feature planning authority to define dependent feature epics. Do not create
replacement children under an incoherent coordinator; preserve user authority, completed work, and real Beads
prerequisites. If no independent value or review boundary is found, continue the same feature.

Use `parent-child` for hierarchy and `blocks` only for real prerequisites. Keep code, tests, and affected documentation
aligned in the same work unit. Record validation and review evidence, include the Beads ID in the commit message, and
close the task only after its acceptance criteria pass. Each task gets exactly one fresh reviewer; fixes resume that
reviewer. A fresh replacement is allowed only when the original is unavailable; material scope changes invalidate the
review and return to specification reconciliation. `/implement-feature` then claims the next ready child and continues
until the implementation coordinator closes. It pauses only when every remaining child is blocked on explicit user
decisions; native planned work should never reach that state. Its final response includes a recommended next step: run
`/close-feature <slug>` when implementation is complete, or provide the named advisement before resuming
`/implement-feature <slug>` when blocked.

Before its startup-version note, `/implement-feature` resolves the authoritative `feat/<slug>` worktree from Git
worktree metadata rather than trusting the process CWD, and scopes all feature Git and Beads mutations to that path. It
requires a clean feature worktree and captures an immutable interaction baseline. It records the root note in a separate
interaction-only audit commit when the export is tracked. It then captures a fresh baseline immediately before each
child claim. Startup alone allows a clean tracked interval when the version note emits no interaction row; child and
coordinator closure still require selected-work-unit evidence. Every child closure and the implementation coordinator
closure is the final Beads mutation in its work-unit interval. The shared verifier requires append-only, valid, unstaged
rows in the selected feature lineage, requires evidence for the selected work unit, rejects intervening interaction
commits, metadata changes, unrelated rows, and other dirty paths, then repeats the checks against the staged index and
the exact pre-staging interaction snapshot. Only `.beads/interactions.jsonl` enters the audit commit. The finalizer
branches on the verified dirty result, pins the pre-commit HEAD and index tree, and verifies the resulting audit
commit's parent, tree, path set, blob, and mode before requiring the feature worktree to be clean before the next child,
coordinator completion, or ordinary return.

These bounded local commits do not authorize remote delivery, worktree removal, or close-out. They preserve feature
history for `/close-feature`, whose later reconciliation still verifies rows created during close-out and delivery.

### Standalone tasks

Use `/implement-task <task-selector>` for exactly one open standalone `task`, `bug`, `chore`, `spike`, or `feature`. It
claims only the selected issue, loads bounded context, validates, runs one fresh reviewer, commits evidence, and closes
that issue. Before its first Beads mutation, it captures a clean worktree and commit baseline. After closure, it
verifies that any tracked `.beads/interactions.jsonl` change is append-only, valid, unstaged, limited to the selected
issue, and untouched by intervening commits. It revalidates the staged index immediately before recording those rows in
a separate interaction-only audit commit. Rewritten, malformed, mode/type-changed, prematurely committed,
commit-then-reverted, unrelated, or mixed dirty state remains blocking and is never restored or absorbed. Invocation
authorizes those bounded local commits but no remote delivery. It does not create feature design or close-out records. A
feature epic or child of a `workflow:feature` epic must use `/start-feature` or `/implement-feature` instead.

Discovered work should retain provenance:

```bash
bd create "Describe discovered work" \
  --type task \
  --deps discovered-from:<current-task-id> \
  --json
```

Add a blocking edge only when the discovery is required for safe completion.

## Close

`/close-feature` compares delivered code with the design and reader-facing docs, creates a standalone
implemented-feature record, and runs validation. One fresh context builder supplies a factual packet to two fresh
holistic reviewers for delivery and drift. They follow the neutrality, extra-source, refresh, confidence-review, and
replacement rules above; fixes resume only the affected reviewer. The workflow then performs an explicit `pr`, `merge`,
or `ready` action. With no mode, it asks which action to take. Merge mode uses `git merge --ff-only` unless the target
repository's `AGENTS.md` explicitly permits merge commits; it never falls back to a merge commit after a failed
fast-forward. Native Beads can append selected-feature rows to the tracked `.beads/interactions.jsonl` in the base
worktree during close-out. Merge mode verifies that this is the only dirty path and that every change is append-only and
belongs to the selected feature molecule or separately identified work with a `discovered-from` or `parent-child` path
back to it, commits those rows on the feature branch, and restores the base copy only after committed preservation.
Delivery and root closures happen after the merge; their interaction rows receive a separate interaction-only commit on
the base branch. Malformed, rewritten, foreign, or mixed dirty state remains blocking. After a confirmed merge,
`/close-feature` runs a mandatory post-merge finalizer: it records the actual merge SHA in the implemented record,
reconciles reader-facing delivery claims, runs `verify-delivery-state.py` and documentation validation, commits the
finalizer, and only then closes delivery and the feature root. A stale merge-pending claim blocks completion.

## Audit

`/audit-project` periodically compares Beads, designs, current docs, implemented-feature records, code, tests, and
recent commits. Recent commit comparison is required read-only Git evidence; it does not authorize Git mutations. If the
execution context denies read-only Git inspection, the audit is explicitly incomplete rather than silently omitting the
comparison. Drift becomes linked Beads work rather than an untracked note.

## Skill maintenance

After editing a canonical skill:

```bash
npx skills update
```
