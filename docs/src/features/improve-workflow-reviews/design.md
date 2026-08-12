# Design — Improve workflow reviews

## Metadata

- Beads feature root: `dstack-mol-2s9`
- Feature slug: `improve-workflow-reviews`
- Design path: `docs/src/features/improve-workflow-reviews/design.md`
- Implemented record: `docs/src/features/improve-workflow-reviews/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Make dstack reviews finite, focused, and enforceable while restoring the intended parallel implementation model:
`/start-feature` validates specification clarity and assembles a safe execution plan; `/implement-feature` dispatches
ready tasks to isolated subagent worktrees, integrates approved commits onto the feature branch by cherry-pick, and
continues through all tasks; `/close-feature` performs the one fresh holistic review after the integrated feature is
complete.

## User Intent

The workflow must keep agents from going off the rails. Reviewers have taken longer over time, context building can take
15 minutes or more, and review/fix rounds can continue without a practical bound. `/start-feature` is supposed to expose
gaps and ambiguity before implementation and stop to ask a precise question instead of silently choosing intent.

Implementation still runs all feature tasks consecutively to completion, but independent ready tasks should execute
concurrently. Each task runs through a subagent in its own worktree. The main agent owns coordination and copies
approved task commits onto `feat/<slug>` by cherry-pick. It starts as many workers as current harness capacity and
physical memory allow, pauses new launches at 80% or greater memory utilization, and resumes fan-out after utilization
falls below 80%. Task workers run focused checks and receive focused reviews. They do not run whole-repository suites.
The fresh-context, holistic review happens after the complete feature has been integrated.

## Goals

- Put enforced wall-clock, idle, context, and review-pass bounds around every reviewer.
- Make unresolved product or architecture intent a structured, user-visible stop in `/start-feature`.
- Minimize reviewer capabilities and provide bounded deterministic evidence packets.
- Remove overlapping review fan-out while preserving independent review where it adds value.
- Have `/start-feature` publish deterministic execution waves from dependencies and declared path ownership.
- Have `/implement-feature` run all ready parallel-safe tasks in isolated worker worktrees and continue until exhausted.
- Gate worker launches on harness capacity and less than 80% physical-memory utilization.
- Make the main agent the sole Beads and feature-branch integration owner.
- Cherry-pick approved task commits in deterministic order.
- Run only focused task validation and focused task review during implementation.
- Run one fresh holistic feature review during close-out.
- Replace prose-only review assertions with executable state and orchestration tests.

## Non-Goals

- Changing the Beads feature identity or lifecycle outside review and implementation orchestration.
- Running implementation workers in containers or claiming OS-level security isolation.
- Scheduling work across multiple machines.
- Predicting a task's future memory use; launch decisions use measured current physical-memory utilization.
- Automatically running the entire repository test suite at any lifecycle stage.
- Preserving the existing four-reviewer start or two-reviewer close topology.
- Allowing task workers to mutate Beads, the feature branch, or other task worktrees.
- Using task-branch merge commits.

## User-Facing Behavior

### `/start-feature`

`/start-feature` performs two non-overlapping specification reviews:

1. **Specification clarity** checks behavior, boundaries, ownership, compatibility, failure/recovery policy,
   documentation intent, and unresolved decisions.
2. **Execution readiness** checks bounded tasks, dependencies, path ownership, focused validation, commit boundaries,
   and parallel safety.

Any ambiguity that would require implementation to invent intent produces `decision_required`, records the affected
requirements and tasks, and asks one precise user question. Specification reconciliation cannot close while that state
is active.

After approval, `/start-feature` computes topological execution waves. Independent tasks with disjoint declared path
ownership may share a wave. Overlapping, ambiguous, or dependent tasks are serialized or returned for specification
repair. The reviewed wave, path ownership, and deterministic integration order are persisted in Beads.

### `/implement-feature`

The main agent remains active until every required implementation task is integrated or a defined blocking state
requires user input. For each ready execution wave it:

1. atomically claims eligible tasks under the shared Beads lease;
2. creates one task branch and linked worktree per task from the current feature integration head;
3. checks harness capacity and current physical-memory utilization before each launch;
4. starts another worker only while utilization is below 80%;
5. lets each worker implement, run focused checks, receive one focused review and at most one fix verification, and
   commit its bounded outcome;
6. validates the returned commit and reviewed diff;
7. cherry-picks successful commits onto `feat/<slug>` in persisted integration order;
8. records evidence and closes the task from the main session;
9. removes a task worktree only after successful integration and evidence capture; and
10. resamples memory and continues launching or integrating until the feature is exhausted.

If physical-memory utilization cannot be measured, execution fails safe to one active worker. At 80% or greater,
existing workers continue, but no new worker starts until another worker completes and utilization is below 80%.

### `/close-feature`

After all task commits are integrated, `/close-feature` reconciles documentation, runs impacted feature-level checks,
builds one bounded deterministic packet for the complete feature diff, and launches one fresh holistic reviewer. That
review covers correctness, security-sensitive behavior, failure/recovery behavior, maintainability, test quality, scope,
design/documentation drift, and accumulated focused evidence. It gets one verification pass for prior findings and
fix-introduced regressions; it cannot begin a third pass.

## Requirements

### Functional Requirements

1. Every reviewer definition has explicit whole-run and idle timeouts, a report threshold, context warning, and timeout
   policy. Timeout is incomplete evidence and cannot authorize automatic retry.
2. Review state permits one initial pass and one focused verification pass. A remaining or new material issue after
   verification stops for redesign, decomposition, waiver, or user guidance.
3. `decision_required` is a first-class blocking review disposition with one precise user question.
4. Reviewer agents load no discovered skills, ordinary extensions, or project context files and have no shell,
   repository mutation, Beads mutation, or subagent-launch capability.
5. Controller-side packet construction uses explicit inputs and stable ordering, with at most 64 inputs, 64 KiB per text
   input, and 256 KiB total output. Limits fail visibly; content is never silently truncated.
6. `/start-feature` uses exactly two initial reviewers: specification clarity and execution readiness.
7. `/implement-feature` uses exactly one focused reviewer per task and no LLM context builder.
8. `/close-feature` uses exactly one fresh holistic reviewer after all task commits are integrated.
9. `/start-feature` persists `execution_wave`, `integration_order`, `owned_paths`, and `parallel_safe` metadata for each
   implementation task.
10. `/implement-feature` launches one worker per eligible task worktree while harness capacity is available and measured
    physical-memory utilization is below 80% immediately before launch.
11. Linux memory utilization is derived from `MemTotal` and `MemAvailable`. macOS uses physical memory and `vm_stat`
    available-page evidence. Unsupported or malformed measurements permit at most one active worker.
12. Workers may edit and commit only in their task worktree. They do not mutate Beads or the feature branch.
13. The main agent is the sole owner of claims, findings/evidence updates, task closure, task cleanup, and integration.
14. Task commits are cherry-picked exactly once in deterministic integration order. Task branches are never merged.
15. Cherry-pick conflicts preserve the worker branch and worktree. Mechanical resolution stays with the main agent;
    behavior-changing resolution returns only the affected task to its worker and focused review boundary.
16. Task validation and review are limited to the task acceptance criteria, declared changed paths, and affected checks.
17. No lifecycle skill automatically runs an entire repository test suite. A full suite runs only by explicit user
    request or separately documented repository delivery policy.
18. Close-out consumes all task evidence and performs impacted feature-level checks plus one holistic review.

### Quality Requirements

- Scheduling, review state, packet construction, and integration decisions are deterministic and behavior-tested.
- Every blocking result is actionable and preserves resumable work without starting replacement agents automatically.
- Long command output stays in ephemeral artifacts; packets contain concise evidence and exact source locations.
- The normal path minimizes model launches and repeated source reads.
- Existing interaction-boundary and append-only Beads evidence invariants remain fail-closed.

### Compatibility and Migration Requirements

- Existing open feature review state must either map unambiguously to the new state machine or stop for explicit
  reconciliation; stale approval cannot be imported.
- Existing planned tasks without path-ownership metadata return to `/start-feature` execution reconciliation before
  parallel dispatch.
- Existing installed Pi reviewer assets update through the owned synchronization mechanism.
- The feature branch remains `feat/<slug>` and delivery remains fast-forward-only.

## Existing Context

Current `/start-feature` serially waits for an LLM context builder and then launches four role reviewers. Current
`/implement-feature` executes directly in the feature worktree, invokes one synchronous task reviewer per child, and
requires a full repository suite before each child commit. Current `/close-feature` builds another LLM packet and runs
two holistic reviewers. Review bounds, packet limits, and most state transitions are prose contracts asserted by string
checks in `tests/test_repository.py`.

The repository already owns:

- append-only review state and findings references under `skills/dstack-core/references/`;
- versioned Pi reviewer assets and a synchronization validator;
- repository-scoped Beads mutation leases and interaction evidence verification;
- linked-worktree discovery and feature-branch verification;
- focused-check guidance and a final close-out lifecycle; and
- a Beads dependency graph suitable for topological execution planning.

## Proposed Design

### Review orchestration module

Add a small stdlib module under `skills/dstack-core/scripts/` that owns legal review transitions, packet manifests,
launch topology, and terminal outcomes. Skills invoke this module and persist its output in Beads instead of
interpreting free-form prose. Reviewer prose remains human-readable supporting evidence.

The state machine is:

```text
initial -> approved
initial -> decision_required
initial -> changes_required -> verification -> approved
initial -> changes_required -> verification -> redesign_required
initial/verification -> unavailable | timed_out
```

There is no transition to a third review pass. A replacement for unavailable infrastructure is not automatic; the
workflow reports the incomplete gate and requires an explicit retry/resume action within the same remaining pass.

### Deterministic evidence packets

The controller supplies a manifest of exact files, Beads JSON, diffs, and command summaries. The packet builder verifies
paths and source boundaries, applies stable ordering, computes identity/digest, and enforces the documented limits. The
context-builder agent is retired or reduced to a no-discovery inventory role; it is not on the normal critical path.

### Parallel execution plan

The execution planner topologically sorts open implementation tasks. A task declares exact or conservative path
ownership. Tasks in the same wave must have no blocker relationship and no ownership overlap. Integration order is
stable within a wave by persisted ordinal and then Beads ID. A graph or ownership change invalidates the plan and
returns to execution reconciliation.

### Worker scheduler

The coordinator samples physical-memory utilization before every launch. Utilization is:

```text
(total physical memory - currently available physical memory) / total physical memory * 100
```

At values below 80%, the scheduler may launch another ready worker when the harness has a free slot. At 80% or greater,
it waits for worker completion and resamples. It never kills healthy workers solely because utilization later rises.
Measurement failure limits the scheduler to one active worker.

Each worker gets a unique `task/<feature-slug>/<task-id>` branch and linked worktree rooted at the current feature
integration head. Its prompt contains only the task boundary, relevant design excerpts, explicit owned paths, focused
validation commands, and output contract. It returns a commit SHA, changed paths, focused evidence, review disposition,
and residual blocker state.

### Integration

The main agent validates each result, waits until its deterministic predecessor is integrated, and cherry-picks the
commit. It rejects merge commits, unexpected paths, stale or mutable reviewed diffs, duplicate integration, and dirty
worktrees. Conflict handling never discards the task branch. Only after successful integration does the main agent
update and close the task under the Beads lease.

## Architecture Consistency

### Existing Patterns Reused

- Beads remains executable work and evidence authority.
- `feat/<slug>` remains the feature integration branch.
- Linked worktrees provide isolated Git mutation boundaries.
- The repository-scoped lease serializes all Beads mutations.
- Review packet IDs, digests, source boundaries, and finding ledgers remain durable.
- Focused checks run while iterating; the close lifecycle owns final feature reconciliation.

### Invariants Preserved

- Workers cannot silently widen their task or make product decisions.
- Shared native Beads state is mutated only by the controlling session under lease.
- A reviewer never edits implementation.
- Every integrated task has an auditable commit and focused validation/review evidence.
- Feature delivery remains explicit and fast-forward-only.

### New Decisions Introduced

- Two start reviews, one task review per task, and one close review replace the existing four/one/two topology.
- Review is capped at initial plus one verification pass.
- Parallel task workers are dynamically admitted below 80% physical-memory utilization.
- Unknown memory state permits one worker rather than unbounded fan-out.
- The main agent cherry-picks task commits; task branches are not merged.
- Whole-repository suites are not automatic lifecycle gates.

### Architecture Documentation Changes

Update `docs/src/architecture/index.md` to describe the coordinator/worker/integrator boundary, review state machine,
evidence packet ownership, and resource-gated fan-out.

## Operational Considerations

- A visible status should report ready, running, waiting-for-memory, waiting-for-integration, blocked, and completed
  task counts without polling subagent session files.
- Memory utilization is sampled only at scheduling events: before launch and after worker completion/failure.
- Worker failure preserves its branch/worktree and reports a resumable task boundary.
- Orphan task worktrees are detectable by feature/task metadata and are never removed before result reconciliation.
- Timeout and memory-gate diagnostics include observed values and the exact blocked action.

## Documentation Impact

| Documentation concern      | Exact page                                            | Create or update | Planned change                                                                 | Owning Beads task                                 |
|----------------------------|-------------------------------------------------------|------------------|--------------------------------------------------------------------------------|---------------------------------------------------|
| Architecture               | `docs/src/architecture/index.md`                      | Update           | Document review state, evidence, coordinator/worker ownership, and integration | `dstack-mol-wrq.2`, `.5`, `.8`, `.9`              |
| Development                | `docs/src/development/feature-lifecycle.md`           | Update           | Document two start reviews, parallel workers, focused checks, and close review | `dstack-mol-wrq.3`, `.6`, `.7`, `.8`, `.9`, `.10` |
| Development                | `docs/src/development/index.md`                       | Update           | Clarify that lifecycle checks are focused and full suites require policy/user  | `dstack-mol-wrq.10`                               |
| Reference                  | `docs/src/reference/index.md`                         | Update           | Document review limits, packet limits, memory threshold, and terminal states   | `dstack-mol-wrq.1`, `.2`, `.5`, `.8`              |
| Navigation                 | `docs/src/SUMMARY.md`                                 | Update           | Register this feature design; no new reader page is added                      | Planning / close-out                              |
| Implemented Feature Record | `docs/src/features/improve-workflow-reviews/index.md` | Create           | Preserve delivery and audit history                                            | `dstack-mol-cba`                                  |

The matching generated-project guidance in `skills/setup-project/template/AGENTS.md.jinja` and
`skills/setup-project/template/docs/src/development/feature-lifecycle.md.jinja` changes with the owning implementation
tasks.

## Validation Strategy

Implementation tasks run their exact focused commands recorded in Beads. The feature-level acceptance evidence includes:

- behavior tests for review transitions, topology, bounded packets, execution waves, memory admission, worktree
  isolation, cherry-pick integration, conflict recovery, focused validation, and holistic close review;
- `uv run --no-project python scripts/check-docs.py` for documentation changes;
- static validation of canonical/generated workflow guidance and Pi reviewer assets; and
- targeted failure injection for timeout, unavailable memory data, threshold crossing, worker failure, stale commits,
  unexpected paths, and cherry-pick conflict.

No automatic full repository test suite is part of this feature's lifecycle acceptance.

## Implementation Decomposition

The implementation coordinator owns ten tasks:

1. enforce reviewer runtime limits;
2. implement the two-pass review state machine;
3. add the blocking `decision_required` gate;
4. minimize reviewer capabilities;
5. build deterministic bounded packets;
6. reduce overlapping review topology and add behavioral orchestration tests;
7. publish deterministic parallel-safe execution waves from `/start-feature`;
8. run memory-gated task workers in isolated worktrees;
9. validate and cherry-pick reviewed task commits from the main agent; and
10. keep task validation/review focused and run one fresh holistic close review.

Beads owns exact dependencies, acceptance, metadata, and live state.

## Dependencies and Parallelism

Reviewer budgets, convergence, and capability isolation may begin independently. Packet construction follows capability
isolation. Decision gating follows convergence and packet construction. Review topology follows convergence, decision
gating, and packet construction. Parallel execution planning follows the start-review topology. Worker fan-out follows
the execution plan and capability isolation. Cherry-pick integration follows fan-out. Focused validation and the final
holistic boundary follow convergence, topology, and integration.

## Rollout and Migration

- Update canonical skills, references, formula, assets, tests, and generated guidance atomically within their owning
  tasks.
- Synchronize versioned Pi reviewers only through the existing explicit installer flow.
- Open features with stale review state stop at reconciliation; they do not receive implicit approval.
- Open task graphs without owned-path metadata are treated as serial until `/start-feature` publishes a reviewed plan.

## Risks and Tradeoffs

- Current memory utilization does not predict worker peak use. The 80% admission gate avoids launching under existing
  pressure but cannot prevent a running worker from growing.
- Path disjointness is necessary but not sufficient for semantic independence. Execution review remains responsible for
  shared behavior, generated files, and migration effects.
- Cherry-picks keep feature history linear but can conflict when independent tasks touch generated or shared output;
  reviewed ownership should serialize those tasks.
- Removing automatic full suites improves latency but makes precise affected-check declarations critical. The holistic
  close review verifies that accumulated focused evidence covers the feature acceptance boundary.

## Rejected Alternatives

- **Run one task per `/implement-feature` invocation:** rejected because the intended workflow completes all tasks and
  can exploit safe concurrency.
- **Always launch all ready tasks:** rejected because harness slots and physical memory are finite.
- **Use a fixed worker count:** rejected in favor of adapting to current harness capacity and memory utilization.
- **Merge task branches:** rejected; the user selected deterministic cherry-pick integration.
- **Keep four start and two close reviewers:** rejected because their evidence gathering overlaps and increases review
  latency.
- **Keep unbounded context-builder discovery:** rejected because it dominates the critical path and has no enforceable
  evidence limit.
- **Run full suites for every task or automatically at close-out:** rejected in favor of focused task/feature evidence
  and one fresh holistic review.

## Open Questions

None.

## Deferred Decisions

None.

## Planning Record

### Questions Asked and Answers

- **How should successful task commits enter the feature branch?** Cherry-pick them; do not merge task branches.
- **How many task workers should run concurrently?** As many as harness capacity permits while physical-memory
  utilization remains below 80%. Stop new launches at or above 80% and resume after pressure falls below 80%.

### Assumptions

- Memory utilization refers to system physical-memory use rather than process RSS, swap use alone, or a fixed worker
  count.
- Existing workers are not killed solely because utilization crosses 80% after launch.
- Unsupported memory measurement should reduce concurrency rather than guess that capacity is available.

### Design Changes During Planning

The initial efficiency review proposed making one child the default `/implement-feature` invocation boundary. The user
rejected that direction and restored the original intended model: all tasks continue through one invocation, safe tasks
run concurrently in isolated subagent worktrees, the main agent integrates by cherry-pick, task validation/review stays
focused, and the holistic fresh review moves to complete-feature close-out.

### Source Material

- User review-efficiency request and follow-up decisions in the current planning session.
- `skills/start-feature/SKILL.md`
- `skills/implement-feature/SKILL.md`
- `skills/close-feature/SKILL.md`
- `skills/dstack-core/references/REVIEW-STATE.md`
- `skills/dstack-core/references/REVIEW-FINDINGS.md`
- `skills/dstack-core/references/PI-REVIEWER-ROSTER.md`
- `skills/dstack-core/assets/pi-reviewers/`
- `.beads/formulas/dstack-feature.formula.toml`
- `docs/src/development/feature-lifecycle.md`
- `tests/test_repository.py`
- `tests/test_pi_reviewer_assets.py`
