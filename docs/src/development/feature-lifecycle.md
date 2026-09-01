# dStack workflow reference

Mutation commands return the native Beads objects they touch. `feature inspect` and `alignment inspect` return the
native root Bead plus deterministic branch/worktree facts; they do not choose the next work item. Use native `bd ready`
as the ready-work surface and `--verbose` only when complete diagnostic records are required. `delivery inspect` remains
the candidate/delivery evidence view.

| Boundary | Native operation | Retry contract |
| --- | --- | --- |
| Plan | Create/update ordinary planned Beads work | Converges from current intent without Git mutation |
| Materialize | Pour the stable formula and create native children | Reuses the unique current root and conventional worktree |
| Authorize | Verify pending content identity, converge planning/gate/approval, then promote it to approved | Only the same content can resume; pending or unidentified partial state is unauthorized |
| Execute | Native atomic ready claim or ownership re-claim, then evidence-backed close | Exact closed work is idempotent; conflicts require current native state |
| Reconcile | Native direct-child fan-in plus documentation/evidence validation | Incomplete validation leaves the terminal boundary open |
| Deliver | Fast-forward Git or registered PR, then Beads finalization | Reinspect uncertain external mutations before retry |

## Feature lifecycle

### `/plan-feature [id|slug|title|request]`

The agent inspects relevant product and repository context, identifies consequential ambiguity, asks focused questions,
and explores material alternatives. It creates or updates one open planned feature Bead whose structured description
preserves the outcome and why, requirements, decisions and rationale, alternatives, non-goals, observable acceptance,
failure and compatibility expectations, documentation expectations, dependencies, and deferred questions.

Planning changes Beads only. It does not pour a molecule, create a branch or worktree, write a design file, create
implementation tasks, or change Git. `/plan-features` is a deprecated thin alias with no separate behavior.

### `/review-feature-spec [feature]`

The controller resolves planned intent or an existing current molecule, then idempotently pours or reuses the stable
workflow and conventional worktree. It claims specification ownership and scaffolds the canonical
`docs/src/features/<slug>/design.md` only when absent. The scaffold stays deliberately lean: Outcome, Non-goals, Design,
Failure/security/compatibility, Validation, and Documentation impact. Required intent, rationale, behavior, interfaces,
risks, and alternatives are captured within those sections only when they materially affect the feature.

The agent reconciles the complete planned intent with current architecture, source, tests, durable docs, dependencies,
and related work. It resolves holes and collisions, refines the canonical design, and creates or updates bounded
implementation outcomes with observable acceptance and real native dependencies. It commits only actual repository
changes using the specification Bead footer, reviews the complete design and graph, and asks for explicit human
authorization. Invocation alone is not approval. After authorization, the controller requires a clean conventional
worktree and tracked design identical to the candidate `HEAD`, writes and verifies its pending content digest, converges
the exact specification, blocking human gate, and approval milestone, promotes the same digest to approved, and clears
pending. Implementation remains unauthorized until the final conjunction is verified.

dStack serializes its own review/scope mutations with approval transitions and refuses those mutations after native
approval until `feature reauthorize` reopens the approval, gate, specification, and workstream boundary. It does not
store a task-graph digest or other shadow graph: Beads remains authoritative, and execution rereads the current native
graph/readiness at each boundary. Re-review reconciles that live graph: valid tasks are reused, obsolete tasks are
closed or superseded, and stale blocking dependencies are removed through Beads.

### Formula-contract compatibility audit

Formula-version drift does not gate implementation or closeout of already approved work; native Beads readiness remains
the execution authority. When an approved active feature is explicitly reviewed under the current `dstack-feature`
semantic contract, the review skill compares its recorded `dstack.formula_version` with the packaged version. The
existing approved molecule remains the complete workflow topology throughout that review.

The feature-review skill compares accepted design and authorized tasks semantically with current planning/review
expectations. The controller emits no skill/routing/resume packet and does not choose the review outcome. If no material
gap exists, the explicit `feature audit-complete` operation stamps only the current version on the feature root. If a
material gap exists, the agent presents only the minimum delta and waits for renewed user authorization before using the
existing `feature reauthorize` plus specification/approval boundary. Historical topology is never rewritten for version
conformity.

### `/implement-feature [feature] [task|--all]`

The controller verifies the design digest and atomically claims the next native ready implementation task. With no task
selector, Beads chooses the singleton candidate directly; dStack does not preselect a stale ready-list entry. An
explicit `--task` remains exact: dStack verifies that requested task is currently ready, then rejects and
verified-releases any different native claim. The agent implements code and tests, defers durable documentation and
reconciliation work, runs focused and task-required checks, reviews and corrects the complete task diff, commits through
the Git helper, verifies the reachable Bead footer and changed paths, then closes only that task. Documentation changes
in an implementation task are rejected; the single closeout task owns the final documentation review. If validation
fails, times out, is interrupted, runs the wrong scope, unexpectedly skips required tests, or substitutes weaker
coverage, the agent reports the exact check and stops before commit or completion.

`--all` repeats only over native ready implementation tasks and stops when none remain. It never closes the
implementation workstream, claims closeout, or starts delivery. If a task intentionally changes no repository content,
finish it with `--no-repository-change --reason "..."`; the native close reason records that outcome for delivery audit.
Ordinary completed tasks still require a reachable Bead footer. Feature and alignment transitions validate the exact
direct parent and work label, delegate open claims to native `ready --claim`, and use native re-claiming to verify
ownership. Feature specification and alignment analysis use the same exact native-ready claim boundary. If a native
claim returns an unexpected issue or a terminal fan-in race appears, dStack restores both open status and an empty
assignee and verifies the reread before reporting recovery. Completion requires a wholly clean worktree, including
untracked files. Empty workstreams close only after their native approval milestone is closed.

### `/close-feature [feature] [ready|pr|merge]`

The controller closes implementation fan-in and claims the one final closeout reconciliation only under this explicit
command. It scaffolds a missing `docs/src/features/<slug>/index.md` without overwriting authored content. The agent
reconciles actual behavior, accepted design, tests, authoritative current-product documentation, and the durable feature
record, then runs the complete repository's full/release validation after any fixups or rebase.

Current mdBook validation requires the foundation, chapter navigation, local links, declared documentation surfaces,
orphan checks, and build to succeed. A docs policy guard rejects namespaced dStack lifecycle fields and structured
identity, Git, worktree, or next-command bookkeeping; generic domain status prose remains valid. An incomplete required
check leaves closeout open and prevents delivery.

- `ready`: stop with an inspected delivery candidate and an open root.
- `pr`: preflight the complete feature diff against a synchronized remote base; the agent drafts the PR from those
  facts; after user approval the controller validates the approved title/body against the aggregate change before the PR
  is created and registered as a native `gh:pr` gate.
- `merge`: perform a clean fast-forward-only delivery and close the root. If the target branch is not currently checked
  out, the controller creates and removes a temporary target worktree for the deterministic delivery operation.
- PR registration is idempotent only for the same unique gate. Conflicting or duplicate gates fail without mutation and
  require explicit `delivery replace-pr` repair with a reason; replaced gates remain native supersession history.
- Direct merge refuses an open or closed unsuperseded PR blocker. Switching modes requires explicit
  `delivery cancel-pr-gate` with a reason; cancellation replaces the blocking edge with native nonblocking context and
  does not modify the GitHub pull request.
- a later `pr` invocation checks the gate and closes the root after merge; PR finalization uses the same
  temporary-worktree behavior when necessary.

The feature catalog links delivered capabilities to `index.md`, which links back to accepted `design.md`. `SUMMARY.md`
keeps one top-level Feature Records section and nests both pages so native mdBook renders them.

Normal delivery requires clean candidate and target worktrees, including untracked files. Before delivery, the candidate
may be amended, fixed up, or rebased; it must remain linear, retain the final terminal footer, and pass the final
documentation/evidence checks. The controller snapshots full Git status around Beads finalization and never creates a
post-delivery bookkeeping commit. If root closure fails or finalization changes HEAD or worktree status after delivery,
the controller reports completed delivery, previous/delivered/observed target heads, root status, finalization error,
and mutation uncertainty. It reopens the Beads root when safe and leaves delivered Git history untouched. Any rollback,
reset, repair, correction, or history rewrite remains a separately authorized native Git operation rather than a dStack
recovery lifecycle.

## Validation layers

Fast tests use a protocol-only Beads stub for command construction and failure handling; they are not authority for
readiness, gates, ownership, or fan-in. Release acceptance uses isolated real-Beads repositories in JSON-envelope mode.
Acceptance preflight fails immediately unless `bd` is available on `PATH`.

## Session boundaries

After a stable boundary, prefer a fresh agent session before starting another substantial independent feature. The new
session must resume from Beads, Git, and durable repository documentation alone; no handoff packet or session state is
required.

### Historical feature graphs

Active historical graphs that do not contain the current four-step molecule remain native Beads records. dStack does
not inspect-and-rewrite them, migrate their children, or translate their dependencies. Complete or retire that work with
native Beads, or explicitly plan a new current feature. Formula compatibility review applies only to a current molecule
and never runs as a hidden eligibility mutation.

## Project-alignment lifecycle

### `/project-alignment-review`

Analyze the current target, decide bounded corrections, and create them beneath the correction workstream. Tier 1 is
read-only for repository source; the plan stores no Git baseline. Finish the plan and leave the human gate open.

### `/project-alignment-execute`

Approved correction scope is immutable. `alignment reauthorize` reopens the native approval, gate, analysis, and
corrections boundary before new corrections can be added; terminal or claimed work requires a superseding workflow
instead. Explicit invocation approves the plan through a convergent native gate and milestone transition, then claims
native ready corrections. Corrections modify code and tests only; the one final landing reconciliation owns durable
documentation. Completing one correction never closes the correction workstream implicitly; after every required
correction is closed or deferred, the explicit finish-workstream step closes the container. The agent uses the same
commit-footer and review rules as feature work, including fixups and rebases before delivery.

### `/project-alignment-land`

Revalidate current repository reality, perform the one final documentation reconciliation, and use the same delivery
controller as features. Landing refuses a dirty worktree and mechanically requires the current mdBook, documentation
policy, and reachable correction evidence audit to pass before the native ready landing step closes. Fixups and rebases
are allowed before delivery when the candidate remains linear and final landing evidence stays reachable. The same
pinned-version compatibility guard used by feature closeout keeps the root open until confirmed delivery. Obsolete or
already-corrected findings are updated or closed based on current evidence; no Git baseline is stored.

## Discovery

- Fix clear in-scope work inside the current task.
- Capture a small incidental follow-up with `bd todo add` and `discovered-from`.
- Create a full task/bug for significant separate work.
- Use a nonblocking relation for context only.

## Review records

By default, write at most one final durable review summary per task or stage. Intermediate comments are reserved for
product decisions, accepted risk, deferred validation, material separate work, or unavailable review that affects
execution.
