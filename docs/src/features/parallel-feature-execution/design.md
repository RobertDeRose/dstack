# Design — Parallel feature execution

## Metadata

- Beads feature root: `dstack-mol-60q`
- Feature slug: `parallel-feature-execution`
- Design path: `docs/src/features/parallel-feature-execution/design.md`
- Implemented record: `docs/src/features/parallel-feature-execution/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Execute reviewed parallel-safe feature tasks concurrently through separate subagent worktrees. `/start-feature`
publishes deterministic waves and ownership. `/implement-feature` remains active until all work is integrated, admits
agents according to harness capacity and physical memory, reviews immutable task commits, and cherry-picks approved
commits onto `feat/<slug>` in deterministic order.

## User Intent

One `/implement-feature` invocation should continue through every feature task. Independent ready tasks should run at
the same time in separate subagent worktrees. The main agent exclusively owns Beads, review orchestration, and
integration. It launches as many agents as harness capacity permits while measured physical-memory utilization is below
80%, pauses new launches at or above 80%, and falls back to one active agent when measurement or capacity cannot be
interpreted. Approved task commits enter the feature branch by cherry-pick, never merge.

## Goals

- Publish reviewed deterministic task waves from dependencies and exact or conservative path ownership.
- Run ready parallel-safe tasks concurrently in separate worker worktrees.
- Use event-driven memory and harness admission without polling subagent session files.
- Keep Beads, focused-review evidence, and integration under the controlling session.
- Attribute concurrent authorized changes without misclassifying sibling progress as contamination.
- Review one immutable commit per task and cherry-pick it exactly once in persisted order.
- Preserve failed, contaminated, or conflicting worktrees for recovery.

## Non-Goals

- Review runtime/state/topology behavior owned by `improve-workflow-reviews`.
- Containers, OS-level security isolation, or malicious-worker prevention.
- Multi-machine scheduling.
- Predicting future worker memory or killing healthy workers after launch.
- Automatically running an entire repository suite.
- Task-branch merge commits.

## User-Facing Behavior

### `/start-feature`

Execution readiness assigns every implementation child:

- exact or conservative `owned_paths`;
- `parallel_safe`;
- topological `execution_wave`;
- deterministic `integration_order`; and
- a plan digest over task IDs, blockers, ownership, and validation commands.

Tasks with dependencies or path overlap cannot share a wave. Missing or ambiguous ownership keeps `spec-reconcile` open.
Graph or ownership drift pauses implementation and reopens the existing reconciliation/review gates; no new lifecycle
gate is added.

### `/implement-feature`

For each ready wave, the controller:

1. claims tasks through short leased Beads intervals;
2. creates `task/<feature-slug>/<task-id>` branches and linked worktrees from the current integration head;
3. registers each task in a wave authority epoch;
4. samples physical memory and atomically asks the harness to admit each launch;
5. runs one bounded worker per admitted task;
6. validates the returned one-commit candidate and focused evidence;
7. releases the worker slot and launches the focused reviewer itself;
8. resumes the worker for fixes and requires an amended replacement commit;
9. verifies the final immutable SHA/digest;
10. cherry-picks approved commits in persisted order;
11. records evidence and closes each task through short leased intervals; and
12. removes a task worktree only after integration and reconciliation-safe cleanup.

Workers never launch reviewers or mutate Beads intentionally. Linked worktrees are a trust-and-verification boundary,
not a sandbox.

## Requirements

### Functional Requirements

1. Planning topologically sorts blocker edges and normalizes exact files, directories, and conservative globs.
2. Same-wave tasks have no dependency and no ownership overlap. Missing ownership is unsafe.
3. Stable integration order is wave, persisted ordinal, then Beads ID.
4. Before each agent launch, memory utilization must be below 80% and the harness must atomically admit a slot.
5. Linux memory uses `MemTotal` and `MemAvailable` from `/proc/meminfo`.
6. macOS total bytes use `sysctl -n hw.memsize`; available bytes are `vm_stat` page size multiplied by `Pages free` +
   `Pages inactive` + `Pages speculative`, capped at total bytes.
7. Missing labels, malformed/zero/impossible values, unsupported platforms, or command failure are unknown and permit at
   most one active task agent.
8. A recognized harness capacity rejection launches nothing and waits for an agent event. If the adapter cannot
   distinguish capacity rejection, concurrency falls back to one.
9. Sampling occurs only before launch and after worker/reviewer completion or failure. Existing agents are not killed
   because later pressure rises.
10. The task-worker profile is a versioned explicit adapter asset. Its mapping, synchronization, discovery, capability
    validation, and tests are owned atomically by the worker-orchestration task.
11. Workers receive no discovered skills/extensions/project context or spawning capability. They receive task CWD, owned
    paths, design excerpt, focused commands, and output contract. Shell access is trusted and bounded by verification,
    not security isolation.
12. A wave authority epoch records controller operations and every admitted sibling task. During a worker interval:
    - changes to registered sibling task refs/worktrees are authorized only when attributable to that sibling's recorded
      phase transition;
    - controller Beads/feature changes are authorized only through signed epoch events under the repository lease;
    - worktree registration/removal is authorized only through controller events; and
    - any unregistered ref, path, interaction, worktree, or feature mutation is contamination.
13. Epoch events include monotonic sequence, actor (`controller` or task ID), operation, before/after digest, and lease
    or agent result identity. Verification replays events between snapshots rather than requiring the whole repository
    to remain unchanged.
14. Interleaving tests accept two sibling commits, controller review-state updates, integration of one task, and
    worktree registration while another worker is active; they reject forged/unattributed equivalents.
15. Contamination stops new launches and integration, preserves all worktrees, and requires operator reconciliation. The
    controller never auto-restores shared authority.
16. The controller owns claims, reviewer launch/resume, findings/evidence, closure, cleanup, and integration.
17. One candidate commit and full diff digest define the focused review boundary. Fixes amend the private task commit;
    verification reviews the replacement SHA/digest.
18. Merge commits, commit ranges, mutable reviewed diffs, unexpected paths, stale plans, duplicate integration, dirty
    authority, or wrong order are rejected.
19. Cherry-pick conflicts are aborted. The affected worker rebases its one-commit result onto current integration HEAD,
    reruns focused checks, and receives verification of a new SHA. The controller never hand-edits an approved commit.
20. Each Beads mutation interval owns one work unit, one clean baseline, and one interaction finalization under the
    repository lease. No baseline spans multiple in-flight tasks.
21. Status reports ready, running, waiting-for-memory, waiting-for-capacity, waiting-for-review,
    waiting-for-integration, blocked, and completed counts without polling session files.
22. Worker/reviewer failure preserves the branch/worktree and reports a resumable state. Feature/task metadata
    identifies orphan worktrees; cleanup requires proven integration and evidence capture.
23. Task checks remain focused and execute the task's exact persisted validation command.

### Quality Requirements

- Planning, memory parsing, admission, epoch attribution, result validation, and integration are behavior-tested.
- Every task has one coherent commit boundary and directly executes its dedicated tests.
- Failure diagnostics include observed memory/capacity, epoch sequence, unexpected delta, and blocked action.
- Existing Beads lease and append-only interaction invariants remain fail-closed.

### Compatibility and Migration Requirements

- Depends on delivered bounded task-review protocol from `improve-workflow-reviews`.
- Existing task graphs without ownership remain serial until `/start-feature` publishes a reviewed plan.
- Existing serial features may continue serially; parallel dispatch requires complete plan metadata.
- Feature branches remain `feat/<slug>` and delivery remains fast-forward-only.

## Existing Context

Current `/implement-feature` executes serially in the feature worktree, launches one task reviewer, requires a full
repository suite, and commits directly. The repository already owns linked-worktree discovery, Beads mutation leases,
interaction reconciliation, reviewer synchronization, and deterministic feature selection. The subagent harness owns
atomic spawn-width slots but dstack does not yet combine those slots with memory admission.

The earlier combined design used whole-repository pre/post snapshots per worker. Review found that such snapshots cannot
distinguish legitimate sibling and controller activity. This design replaces that model with phase-attributed wave
epochs.

## Proposed Design

Use three narrow stdlib helpers:

- `plan-execution.py` computes and validates plans;
- `task-scheduler.py` parses memory evidence, owns wave epoch records, and decides admission; and
- `validate-task-result.py` validates immutable commits, epoch attribution, paths, order, and cleanup eligibility.

Skills remain controllers. Helpers return structured data and never mutate Beads or Git independently.

### Controller-owned task protocol

```text
planned → claimed → worker_running → candidate → review_running → fixes_required
→ worker_fixing → verification_running → approved → waiting_for_integration
→ integrated → evidenced → closed
```

The worker owns source edits, focused checks, and its private one-commit result. The reviewer is read-only. Controller
epoch events authorize shared-state transitions while sibling agents remain active.

### Wave authority epoch

The controller captures a wave baseline after task worktrees are registered. Every authorized operation appends a
structured event to an ephemeral controller ledger whose digest and terminal summary are persisted in Beads. Task result
validation compares snapshots by replaying events for all registered actors. It never assumes sibling refs, worktrees,
or controller state are static. Unknown deltas fail closed.

## Architecture Consistency

### Existing Patterns Reused

- `feat/<slug>` integration branch and `task/<feature-slug>/<task-id>` task branches.
- Repository-scoped Beads mutation lease and interaction reconciliation.
- Controller-owned review state and immutable source boundaries.
- Explicit Pi adapter asset synchronization.
- Focused task validation from the bounded-review feature.

### Invariants Preserved

- Workers do not own shared workflow authority.
- Reviewers never edit implementation.
- Every integrated task has one approved commit and focused evidence.
- Concurrent authorized changes remain attributable.
- Unknown shared-authority changes stop without destructive recovery.

### New Decisions Introduced

- Event-attributed wave epochs replace impossible globally static snapshots.
- Harness slot acquisition is the authoritative capacity decision.
- Unknown memory/capacity permits one active task agent.
- Conflicts always return to worker/reviewer rather than controller edits.

### Architecture Documentation Changes

Update `docs/src/architecture/index.md` with coordinator/worker/integrator ownership, wave epochs, adapter boundary, and
immutable integration.

## Operational Considerations

`docs/src/operations/index.md` documents status, memory/capacity diagnostics, worker failure, epoch contamination,
preserved worktrees, orphan detection, conflict return, and cleanup. Scheduling is event-driven and never polls session
files.

## Documentation Impact

| Concern                | Exact page                                                                      | Change          | Planned content                                                           | Owning task                       |
|------------------------|---------------------------------------------------------------------------------|-----------------|---------------------------------------------------------------------------|-----------------------------------|
| Architecture           | `docs/src/architecture/index.md`                                                | Update          | Waves, epochs, controller/worker ownership, immutable integration         | Worker/integration tasks          |
| Operations             | `docs/src/operations/index.md`                                                  | Update          | Status, memory/capacity, contamination, failure, orphan/conflict recovery | Worker/integration tasks          |
| Development            | `docs/src/development/feature-lifecycle.md`                                     | Update          | Planning, fan-out, focused handoff, integration                           | All implementation tasks          |
| Reference              | `docs/src/reference/index.md`                                                   | Update          | Plan fields, memory formula, task states, epoch schema                    | Planning/worker tasks             |
| Generated policy       | `skills/setup-project/template/AGENTS.md.jinja`                                 | Update          | Worker/controller/integration rules                                       | Worker task                       |
| Generated lifecycle    | `skills/setup-project/template/docs/src/development/feature-lifecycle.md.jinja` | Update          | Generated parallel lifecycle                                              | Planning/worker/integration tasks |
| Roadmap                | `docs/src/planned-features.md`                                                  | Update          | Dependency and prospective/delivered state                                | Planning / close-out              |
| Design navigation      | `docs/src/SUMMARY.md`                                                           | Update          | Register design                                                           | Planning                          |
| Implemented navigation | `docs/src/SUMMARY.md` and `docs/src/features/index.md`                          | Update at close | Register delivered record                                                 | `dstack-mol-a0u`                  |
| Implemented record     | `docs/src/features/parallel-feature-execution/index.md`                         | Create at close | Delivery and audit history                                                | `dstack-mol-a0u`                  |

Every documentation-changing task runs `uv run --no-project python scripts/check-docs.py`.

## Validation Strategy

- `tests/test_execution_plan.py` tests DAG, ownership, drift, waves, and order.
- `tests/test_task_scheduler.py` tests Linux/macOS parsing, 79.99%/80% boundaries, unknown fallback, capacity outcomes,
  event scheduling, worker/reviewer slot sequencing, and status/recovery.
- `tests/test_wave_authority.py` tests authorized sibling/controller interleavings, event replay, forgery,
  contamination, and preserved recovery.
- `tests/test_task_integration.py` tests immutable commits, unexpected paths, stale plans, duplicates, order, conflict
  return, partial waves, and cleanup.
- `tests/test_reconcile_beads_interactions.py` covers leased one-work-unit finalization and snapshot races.
- `tests/test_pi_reviewer_assets.py` covers the worker adapter, explicit sync, and capability constraints.
- `uv run --no-project python scripts/check-docs.py` validates documentation.

No automatic full repository suite is part of this feature lifecycle.

## Implementation Decomposition

1. Publish deterministic parallel-safe plans and drift repair.
2. Implement the worker adapter, memory/capacity admission, event-driven scheduler, wave epoch attribution,
   worker/reviewer handoff, status, and recovery.
3. Validate and cherry-pick immutable reviewed commits, return conflicts, finalize interactions, and clean worktrees.

## Dependencies and Parallelism

The feature root depends on `improve-workflow-reviews`. Planning precedes worker orchestration; orchestration precedes
integration. These three tasks are deliberately serial because they share lifecycle skills and each consumes the prior
contract. Runtime task concurrency is the delivered behavior, not the implementation decomposition.

## Rollout and Migration

- Serial features remain supported.
- `/start-feature` publishes plan metadata before parallel dispatch is allowed.
- First parallel use captures an epoch and verifies all registered task actors before integration.
- Any adapter, memory, capacity, or attribution uncertainty falls back to serial or stops visibly.

## Risks and Tradeoffs

- Epoch attribution is more machinery than static snapshots, but static snapshots are incorrect under legal concurrency.
- Current memory pressure cannot predict worker peaks.
- Trust-and-verification detects but does not prevent malicious shared-repository mutation.
- Cherry-pick conflict recovery costs another focused worker/reviewer cycle but preserves review integrity.

## Rejected Alternatives

- **Globally static worker snapshots:** rejected because sibling/controller activity creates false contamination.
- **Serialize all shared activity while workers run:** rejected because it undermines useful concurrency and delays
  integration/review progress.
- **Worker-launched reviewers:** rejected because nested launches obscure authority and can deadlock capacity.
- **Main-agent conflict edits:** rejected because they invalidate the reviewed commit.
- **Merge task branches:** rejected; the user selected cherry-pick.
- **Fixed worker count:** rejected in favor of harness and memory admission.

## Open Questions

None.

## Deferred Decisions

None.

## Planning Record

### Questions Asked and Answers

- **How should task commits enter the feature branch?** Cherry-pick, never merge.
- **How many agents run?** As many as harness admission permits while physical memory is below 80%; unknown evidence
  permits one.
- **Should parallel execution remain in the review-lifecycle feature?** No; create this dependent feature.

### Assumptions

- The harness exposes atomic admission through launch success or a recognizable capacity rejection.
- The bounded-review feature supplies deterministic focused review and finite verification.
- Controller epoch event integrity can be tied to lease/result identities and persisted terminal digests.

### Design Changes During Planning

The scope was extracted from `improve-workflow-reviews` after review found an independent architecture and delivery
boundary. Whole-repository static contamination snapshots were replaced with phase-attributed wave epochs.

### Source Material

- User decisions and both combined-feature specification review rounds.
- `docs/src/features/improve-workflow-reviews/design.md`
- `skills/implement-feature/SKILL.md`
- `skills/start-feature/SKILL.md`
- `skills/dstack-core/references/INTERACTION-BOUNDARY.md`
- Pi subagent spawn-width and timeout runtime implementation.
- `tests/test_reconcile_beads_interactions.py`
