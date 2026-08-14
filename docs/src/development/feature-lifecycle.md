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

`/start-feature <slug>` resolves the human reference, activates `feat/<slug>`, derives two direct assignments from
Beads, design/docs, and an immutable Git source boundary, and launches exactly two fresh independent reviewers
concurrently:

1. specification clarity for behavior, boundaries, compatibility, ownership, recovery, documentation intent, and
   unresolved decisions;
2. execution readiness for task scope, dependencies, ownership, validation, acceptance, and commit boundaries.

There is no LLM context builder. Missing Pi names use the explicit project-local sync from `sync-pi-reviewers.py`; a
declined or failed sync has no silent role substitution. The optional Pi adapter maps these roles to
`dstack-clarity-reviewer` and `dstack-readiness-reviewer`; missing names use the explicit optional sync or fail visibly
without substitution. Close-out maps `implementation-integrity` and `delivery-integrity` to their specialized reviewers.
Beads stores executable per-reviewer state and findings. The aggregate gate requires both reviewers, invalidates
overlapping provisional approval, permits one verification pass, and keeps unresolved
decisions/findings/infrastructure/waivers/ redesign blocking. Decision briefs explain the issue, affected
requirement/task IDs, evidence or uncertainty, recommendation, alternatives and consequences, and exactly one precise
question; the answer, author, and reviewed diff digest are durable before the only verification pass. The aggregate gate
cannot close unless `can_close` is true.

Old four-start/two-close graphs migrate only through `migrate-review-topology.py` from the canonical primary worktree.
The leased migration preserves evidence as superseded history, rewires gates, writes/verifies a cutover marker,
transfers no approval, and is idempotent. Stale controllers fail closed.

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
aligned in the same work unit. Run the exact task validation persisted in Beads and documentation checks when docs
change. Validation and one focused reviewer are bounded by the exact task acceptance criteria, declared changed paths,
and affected checks. The implementation lifecycle does not automatically run the entire repository suite; run it only
after an explicit user request or when a separate repository delivery policy requires it. Record validation and review
evidence, include the Beads ID in the commit message, and close the task only after acceptance passes. Fixes resume the
same reviewer. A fresh replacement is allowed only when the original is unavailable; material scope changes invalidate
the review and return to specification reconciliation. `/implement-feature` then claims the next ready child and
continues until the implementation coordinator closes. It pauses only when every remaining child is blocked on explicit
user decisions; native planned work should never reach that state. Its final response includes a recommended next step:
run `/close-feature <slug>` when implementation is complete, or provide the named advisement before resuming
`/implement-feature <slug>` when blocked.

Before its startup-version note, `/implement-feature` resolves the authoritative `feat/<slug>` worktree from Git
worktree metadata rather than trusting the process CWD. Native linked-worktree Beads authority is shared, so `bd -C` is
not an isolation boundary. Every Beads mutation interval uses the repository-scoped interaction lease from
`dstack-core/references/INTERACTION-BOUNDARY.md`; the lease is outside Git and prevents concurrent mutation races. It
requires a clean feature worktree and captures an immutable interaction baseline. It records the root note in a separate
interaction-only audit commit when the export is tracked. It then captures a fresh baseline immediately before each
child claim. Startup alone allows a clean tracked interval when the version note emits no interaction row; child and
coordinator closure still require selected-work-unit evidence. Every child closure and the implementation coordinator
closure is the final Beads mutation in its work-unit interval. The shared verifier requires append-only, valid, unstaged
rows in the selected feature lineage, requires evidence for the selected work unit, rejects intervening interaction
commits, metadata changes, foreign interaction rows, and other dirty paths. It repeats the checks against the staged
index and the exact pre-staging interaction snapshot. Only `.beads/interactions.jsonl` enters the audit commit. The
finalizer branches on the verified dirty result, pins the pre-commit HEAD and index tree, and verifies the resulting
audit commit's parent, tree, path set, blob, and mode before requiring the feature worktree to be clean before the next
child, coordinator completion, or ordinary return.

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

`/close-feature` reconciles docs and derives impacted checks from design validation, child evidence, changed-path
ownership, generated/docs parity, and checks invalidated by fixes. It reuses unchanged focused evidence and does not
implicitly run the whole repository suite. It then derives two direct close assignments from Beads, design/docs,
validation evidence, and the immutable Git source boundary. Implementation-integrity covers correct code behavior,
quality and simplicity, security, and maintainability; delivery-integrity covers documentation, validation evidence,
Beads state, implemented records, roadmap/navigation, delivery claims, and drift. Both reviewers use the pinned
nicobailon definition with a 600,000 ms whole-run deadline, fresh read-only context, and persisted session/output
completion evidence. Each has at most one verification pass per boundary; there is no third pass. Timeout or
unavailability preserves incomplete evidence and permits only one explicit same-pass infrastructure replacement per
role. A second failure stops that role's boundary; after a committed redesign, the executable `redesign` transition
requires a new reviewed source boundary before starting one new initial review. Pane state and shell sentinels are
transport evidence, not completion authority. Protected security, correctness, validation, accessibility, and
data-loss-protection findings are never waivable; any eligible waiver binds the exact non-material finding and user
rationale. Assignment/elapsed/context/replacement telemetry is operational evidence, not approval. The optional Pi
adapter maps the close roles to `dstack-implementation-reviewer` and `dstack-delivery-integrity-reviewer`. Delivery
remains an explicit PR, fast-forward merge, or ready action. Delivery and root closures happen after the merge, only
after post-merge finalization records actual delivery evidence.

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
