# dStack workflow reference

Mutation commands return the root identifier and the native objects they touch. Use `feature inspect`,
`alignment inspect`, or `delivery inspect` when the full current dashboard is required; mutations do not hydrate
unrelated ready work or progress.

## Feature lifecycle

### `/start-feature [id|slug|title]`

`dstackctl feature initialize` resolves an existing current feature or pours one
new molecule and creates/reuses its conventional worktree. The agent writes the
design and decides task decomposition. `feature scaffold-design` also adds the
design to the mdBook summary and feature index. `dstackctl feature add-task`
performs the mechanical task creation.

No Git commit is required. No roadmap execution status is changed. Every feature
design uses `docs/src/features/<slug>/design.md`, the mdBook feature directory.

### `/review-feature-spec [feature]`

The controller claims the specification step. The agent reviews design intent,
implementation boundaries, tasks, dependencies, documentation impact, and
validation. It commits only actual repository changes using the specification
Bead footer. Approval records the design-content digest, resolves the human
gate, and closes the approval milestone idempotently.

### `/implement-feature [feature] [task|--all]`

The controller verifies the design digest and atomically claims the next native
ready implementation task. The agent implements, runs focused and task-required
checks, reviews and corrects the complete candidate diff, commits through the
Git helper, verifies the reachable Bead footer and changed paths, then closes
only that task. If validation fails, times out, is interrupted, runs the wrong
scope, unexpectedly skips required tests, or substitutes weaker coverage, the
agent reports the exact check and stops before commit or completion.

`--all` repeats only over native ready implementation tasks and stops when none
remain. It never closes the implementation workstream, claims closeout, or
starts delivery. If a task intentionally changes no repository content, finish
it with `--no-repository-change --reason "..."`; the native close reason records
that outcome for delivery audit. Ordinary completed tasks still require a
reachable Bead footer.

### `/close-feature [feature] [ready|pr|merge]`

The controller closes implementation fan-in and claims closeout only under this
explicit command. The agent reconciles actual behavior, tests, and durable
documentation, then runs the complete repository's full/release validation. An
incomplete required check leaves closeout open and prevents delivery. A docs
policy guard rejects namespaced dStack lifecycle fields and structured identity,
Git, worktree, or next-command bookkeeping; generic domain status prose remains
valid. The closeout step is then closed.

- `ready`: stop with an inspected delivery candidate and an open root.
- `pr`: preflight the complete feature diff against a synchronized remote base; the agent drafts the PR from those
  facts; after user approval the controller validates the approved title/body against the aggregate change before the PR
  is created and registered as a native `gh:pr` gate.
- `merge`: perform a clean fast-forward-only delivery and close the root.
- a later `pr` invocation checks the gate and closes the root after merge.

Normal delivery snapshots tracked Git state around Beads finalization and fails
if finalization changes HEAD or tracked status. It never creates a post-delivery
bookkeeping commit. If a failed or incorrect delivery needs rollback, reset,
repair, correction, or history rewrite, the user must authorize that separate
native Git operation; it is not a dStack recovery lifecycle.

## Validation layers

Fast tests use a protocol-only Beads stub for command construction and failure handling; they are not authority for
readiness, gates, ownership, or fan-in. Release acceptance uses isolated real-Beads repositories in JSON-envelope mode.
Acceptance preflight fails immediately unless `bd` is available on `PATH`.

## Session boundaries

After a stable boundary, prefer a fresh agent session before starting another substantial independent feature. The new
session must resume from Beads, Git, and durable repository documentation alone; no handoff packet or session state is
required.

## Project-alignment lifecycle

### `/project-alignment-review`

Analyze the current target, decide bounded corrections, and create them beneath the correction workstream. Tier 1 is
read-only for repository source. Finish the plan and leave the human gate open.

### `/project-alignment-execute`

Explicit invocation approves the plan. The controller resolves the gate and
claims native ready corrections. The agent implements each correction using the
same commit-footer and review rules as feature work.

### `/project-alignment-land`

Revalidate current repository reality, reconcile durable docs, and use the same
delivery controller as features. There is no stored baseline commit; obsolete
or already-corrected findings are updated or closed based on current evidence.

## Discovery

- Fix clear in-scope work inside the current task.
- Capture a small incidental follow-up with `bd todo add` and `discovered-from`.
- Create a full task/bug for significant separate work.
- Use a nonblocking relation for context only.

## Review records

By default, write at most one final durable review summary per task or stage. Intermediate comments are reserved for
product decisions, accepted risk, deferred validation, material separate work, or unavailable review that affects
execution.
