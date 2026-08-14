# Design — Improve workflow reviews

## Metadata

- Beads feature root: `dstack-mol-2s9`
- Feature slug: `improve-workflow-reviews`
- Design path: `docs/src/features/improve-workflow-reviews/design.md`
- Implemented record: `docs/src/features/improve-workflow-reviews/index.md`
- Base branch: `main`
- Status: redesign in progress

## Feature Summary

Make dstack review lifecycles finite, focused, deterministic, recoverable, and easy to operate. The controller remains
responsible for assembling the review context from the workflow authorities and launching specialized read-only
reviewers directly. Beads is the workflow manifest; a separate evidence collector, content packet, or shared reviewer
context-builder is not part of the design.

The feature owns reviewer runtime budgets, executable two-pass state, unresolved-intent gating, direct specialized
review roles, focused validation, old-graph migration, and explicit close-out review. Parallel task execution remains a
separate dependent feature.

The repository already contains an earlier packet-based implementation boundary. That boundary is historical. The
redesign implementation is present on this feature branch but remains pre-delivery until implementation tasks, focused
validation, and both specialized close reviews finish. The redesign is a new specification boundary, not a third review
pass on the old boundary.

## User Intent

Review orchestration must be finite and reliable without treating terminal or pane transport state as completion
authority. Reviewers should receive narrowly defined purposes and inspect the relevant source themselves. A failed or
missing specialist must not block unrelated specialists through a serialized evidence-collection step. `/start-feature`
must explain unresolved intent, recommend a choice, and ask one precise user question rather than silently choosing or
merely reporting an opaque blocking state.

Task validation and review remain focused. Whole-repository suites are not automatic lifecycle gates. Workflow-level
reviewer-budget overrides remain deferred until canonical defaults demonstrate a real limitation.

## Goals

- Keep Beads as the executable workflow manifest and durable review authority.
- Have the controller derive small role assignments from Beads, the design/docs, and a pinned Git source boundary.
- Launch independent specialized reviewers directly, without a collector subagent, LLM context builder, shared content
  packet, or union-of-all-review-inputs projection.
- Give every reviewer an explicit purpose, scope, non-goals, declared paths/domains, and report contract.
- Preserve one initial pass and one verification pass per review boundary, with explicit infrastructure replacement and
  redesign accounting.
- Use two independent close-out reviewers: implementation integrity and delivery integrity.
- Retain focused task validation, source-boundary binding, append-only evidence, and fail-closed delivery.
- Migrate old review graphs without transferring old approvals or losing historical evidence.

## Non-Goals

- Parallel implementation workers, execution waves, memory admission, worker worktrees, or cherry-pick integration.
- A new packet format, evidence bundle, context-builder role, or collector subagent.
- A second Beads-like manifest or durable controller-owned copy of issue acceptance criteria.
- Workflow-level reviewer-budget overrides.
- OS-level process isolation.
- Automatically running a full repository suite.

## Authority Model

Each authority answers one question:

- **Beads** owns feature identity, lifecycle gates, task graph, dependencies, ownership, acceptance criteria, review
  state, findings, validation notes, and close-out status. It is the workflow manifest.
- **Design and reader-facing docs** own intended behavior and supported documentation contracts.
- **Git** owns the immutable reviewed commit, diff base, changed paths, and complete diff digest.
- **The controller** derives a transient role assignment from those authorities, pins the source boundary, launches
  reviewers, and persists their reports. The assignment is not a competing authority.
- **Reviewers** provide read-only evidence and findings. They never mutate Beads, Git, files, or Pi configuration.

The controller must not copy all Beads history or source content into a packet. It reads the selected Beads records and
current append-only projections, derives the assignment, and records the source-boundary identity in the owning review
bead. Reviewer prompts may repeat the bounded metadata needed to execute a review, but prompts and transcripts remain
supporting evidence.

## Existing Context

The earlier implementation used `build-review-packet.py` to assemble one deterministic base packet and role projections,
then launched narrow reviewers against those projections. Close-out used one overloaded holistic role. That
implementation and its Beads history remain valid historical evidence and are not erased by this redesign. The direct-
review design is a new boundary because changing reviewer purpose, assignment, and close topology is material behavior.

The repository already has pure review-state and aggregate helpers, a leased Beads topology migrator, focused validation
policy, and read-only Pi reviewer assets. Those remain useful seams. The packet provider and its consumers are the
serialization seam being removed; Beads and Git already provide the durable workflow and source authorities needed by
the controller.

## Proposed Design

Keep the state machine, findings ledger, runtime isolation, source-boundary checks, interaction lease, and focused
validation contracts. Replace content collection with direct controller-to-reviewer assignments. Each assignment is
small enough to derive from the owning Beads issue and current Git boundary, and each reviewer independently gathers
only its declared evidence from a pinned read-only worktree.

Keep the two start roles and one task role. Replace the holistic close role with two concurrent close roles whose scopes
are intentionally disjoint: implementation integrity owns correct code behavior, quality and simplicity, security, and
maintainability; delivery integrity owns documentation, validation evidence, Beads state, implemented records,
roadmap/navigation, delivery claims, and drift. The controller aggregates their durable Beads states without asking an
LLM to perform a final content review.

## Architecture Consistency

### Existing Patterns Reused

- Beads remains the live workflow manifest, dependency graph, and review authority.
- Git remains the immutable reviewed-source authority.
- Pure state validation remains separate from leased Beads graph mutation.
- Reviewer assets remain explicitly synchronized and read-only.
- Focused validation remains the lifecycle evidence policy.

### Invariants Preserved

- Reviewers cannot mutate repository or workflow state.
- Infrastructure failure never implies approval.
- User intent is never invented.
- Old evidence remains attributable and old approval never transfers.
- One initial plus one verification pass remains the maximum for one boundary.
- Delivery remains explicit and fast-forward-only.

### New Decisions Introduced

- Beads is the manifest; no second durable review-content manifest is introduced.
- The controller derives transient assignments rather than building shared content packets.
- Close-out requires implementation-integrity and delivery-integrity reviewers instead of one holistic reviewer.
- A collector failure cannot block unrelated specialists because no collector is launched.

### Architecture Documentation Changes

Architecture, operations, lifecycle, reference, root policy, reviewer roster, formula, and generated guidance describe
the direct-assignment implementation on this feature branch. The roadmap and implemented record remain explicitly
pre-delivery until validation, both specialized close reviews, and delivery finish.

## Operational Considerations

Operators diagnose review progress from the owning Beads issue, immutable Git source-boundary fields, reviewer session
artifacts, and current state/findings records. A missing or unavailable specialist blocks only that role; the controller
may use the one explicit same-pass infrastructure replacement allowed by the state machine. A material fix requires a
new source boundary and targeted reviewer verification. A material redesign requires a committed design boundary and the
single bounded redesign transition. No delivery action is available until both close roles and the structural aggregate
pass.

## Direct Review Flow

Before launch, the controller:

1. resolves the human feature/task selector and relevant Beads issue IDs;
2. acquires the repository interaction lease for Beads mutations and verifies the clean authoritative worktree;
3. records the exact installed skill version before mutation;
4. pins `review_boundary_id`, `reviewed_commit`, `reviewed_diff_base`, `reviewed_diff_digest`, and changed paths from
   Git;
5. reads the design sections, Beads acceptance/dependencies, and current validation evidence needed by each role;
6. derives one bounded assignment per reviewer; and
7. persists `initial_active` review state before launching any reviewer.

The controller launches independent reviewers concurrently when the workflow has more than one role. A reviewer
assignment contains only:

- the owning Beads issue ID and human title;
- the relevant description, acceptance criteria, dependencies, and validation commands;
- the immutable Git source-boundary fields;
- declared paths, domains, requirement IDs, and explicit non-goals; and
- the required structured report shape.

The reviewer reads the pinned read-only worktree and the assigned paths. It does not wait for another reviewer or ask a
collector to assemble evidence. If the assignment is insufficient, the reviewer reports the exact missing evidence; the
controller records that as incomplete evidence or a finding according to the state contract. The controller does not
silently broaden the assignment.

## Specialized Reviewer Roles

### Specification clarity

Reviews behavior, boundaries, compatibility, ownership, failure and recovery policy, documentation intent, and
unresolved user decisions. It does not review task decomposition except where decomposition exposes invented product
intent.

### Execution readiness

Reviews task scope, dependency direction, ownership, validation, documentation ownership, acceptance criteria, and
commit boundaries. It confirms work is executable without inventing intent.

### Task reviewer

Reviews one selected task or standalone issue for correct behavior, security-sensitive behavior, failure/recovery, test
adequacy, documentation alignment, scope compliance, and compliance with that issue's acceptance criteria. It does not
expand the task or invent product policy.

### Implementation integrity

Reviews **correct code behavior, quality and simplicity, security, maintainability**. It examines implementation paths,
tests, failure behavior, and security-sensitive changes within the feature's reviewed source boundary. It does not own
delivery documentation, Beads lifecycle status, or release claims except when a code change makes those claims unsafe.

### Delivery integrity

Reviews documentation, validation evidence, Beads state, the implemented record, roadmap/navigation, delivery claims,
and cross-artifact drift. It does not duplicate the implementation-integrity review of code behavior, quality and
simplicity, security, or maintainability.

The close-out aggregate requires both `implementation-integrity` and `delivery-integrity`. There is no overloaded
holistic reviewer and no final LLM collector. The controller performs the final structural check: required reviewer IDs,
current Beads states, common source boundary, current findings, delivery prerequisites, and `can_close`.

## User-Facing Behavior

### Reviewer runtime

Every reviewer uses nicobailon/pi-subagents with a 600,000 ms whole-run deadline, fresh context, no inherited project
context or skills, an empty extension allowlist, read-only acceptance, and only declared read-only tools. There is no
idle-timeout or report-only wrap-up equivalent. Saved session/output artifacts and bounded wait/status results are
completion evidence; terminal panes and shell sentinels are presentation/transport only. Timeout or transport errors
preserve incomplete evidence and never authorize approval or automatic retry.

### `/start-feature`

The controller reads the design issue, implementation graph, and the two review beads from Beads, derives the pinned
source boundary, and launches exactly two independent reviewers:

1. specification clarity; and
2. execution readiness.

Beads records each role's state and findings. The aggregate requires both exact reviewer IDs. Initial approval is
provisional until aggregate reconciliation finishes. A sibling change overlapping a declared path, domain, or
requirement invalidates only the affected initial approval and consumes that reviewer's verification pass. Disjoint
changes do not invalidate approval. No packet or shared evidence collector participates.

When implementation would need to invent intent, the controller records `decision_required` and presents a concise
decision title, issue, affected requirement/task IDs, evidence and uncertainty, recommendation, alternatives and
consequences, and exactly one precise question. The answer is persisted in Beads and the design before verification.

### `/implement-feature` and `/implement-task`

Each selected task receives one focused task reviewer directly from the controller. The assignment is derived from the
selected Beads issue, its design links, changed paths, and affected checks. Review is limited to that task's acceptance,
changed paths, affected checks, and regressions introduced by fixes.

### `/close-feature`

After documentation reconciliation and impacted feature checks, close-out launches two fresh reviewers concurrently:

1. implementation integrity; and
2. delivery integrity.

Each reviewer reads only its declared role scope in the pinned worktree. Both reports and current Beads states are
required before delivery can proceed. The controller's structural aggregate check is deterministic and does not review
content on behalf of either role.

## Requirements

### Functional Requirements

1. Canonical nicobailon/pi-subagents reviewer defaults are:
   - `timeoutMs: 600000` (a 600-second whole-run deadline);
   - `defaultContext: fresh`;
   - `inheritProjectContext: false`;
   - `inheritSkills: false`;
   - an empty `extensions` allowlist;
   - `acceptanceRole: read-only`; and
   - bounded status/wait operations that report incomplete evidence without approval or automatic retry.
2. Completion is determined from persisted session/output and lifecycle artifacts, not a shell or terminal sentinel.
   Timeout or transport errors are incomplete evidence and never approval or automatic retry by themselves.
3. Reviewer definitions have no discovered skills, ordinary extensions, project context, shell, mutation tools, or
   spawning. Each role has a narrow purpose, declared domains, explicit non-goals, and exact report contract.
4. Beads is the manifest. The controller must derive role assignments from current Beads/design/Git authority and must
   not create a second durable content manifest, evidence packet, collector bundle, or union-of-all-inputs projection.
5. Every review state binds to `review_boundary_id`, `reviewed_commit`, `reviewed_diff_base`, `reviewed_diff_digest`,
   the owning Beads review issue, and declared paths/domains/requirement IDs. Packet and projection IDs/digests are not
   required in the redesigned state contract.
6. Review telemetry records reviewer wall time, context usage when reported, terminal status, replacement cause, and
   bounded assignment/path counts when available. Collector packet byte/input metrics are removed. Telemetry is
   evidence, not approval.
7. Review state permits one initial pass and one verification pass. No third pass is legal.
8. Durable schema uses separate counters:
   - `redesign_replacement_count`: zero or one per design boundary; and
   - `infrastructure_replacement_count`: zero or one per pass.
   Existing v1 replacement data remains historical and cannot imply approval.
9. Timeout or unavailability enters an incomplete state in either pass. One explicit same-pass infrastructure
   replacement is permitted when its counter is zero. A second infrastructure failure is terminal.
10. Failed verification with eligible findings enters `waiver_required`, preserving findings while awaiting the user.
    User acceptance produces `approved_with_waiver`; user refusal produces `redesign_required`.
11. Protection is independent of severity: security, correctness, validation, accessibility, and data-loss-protection
    findings are non-waivable. Other findings are waivable only when explicitly non-material and all waiver evidence is
    recorded.
12. `decision_required` records affected requirement/task IDs, question, recommendation, alternatives, answer, answer
    author, and a boundary digest equal to the current `reviewed_diff_digest`. Resolved decision evidence remains
    retained after verification begins.
13. A workflow cannot close its review reconciliation while a decision, ordinary finding, incomplete review, waiver, or
    redesign state is active in any required reviewer or the aggregate.
14. The aggregate records exact reviewer IDs, declared domains/paths, current dispositions, compound pending conditions,
    reconciliation change set, and invalidated approvals. It requires a common source boundary but no role projection
    identities or packet update list. Reconciliation updates the current Beads states atomically before overlap
    invalidation; partial reviewer-state writes fail closed.
15. Required reviewer sets are:
    - start: `specification-clarity`, `execution-readiness`;
    - task: `task`; and
    - close: `implementation-integrity`, `delivery-integrity`.
16. Existing four-start/two-close molecules migrate fail-closed:
    - old review records and findings remain append-only history;
    - root metadata receives the new logical reviewer IDs;
    - obsolete review beads become `superseded` only after their evidence is mapped;
    - blocker edges are rewired under the repository Beads lease;
    - old approvals never imply new approval; and
    - migration is idempotent and verified at start, implementation resumption, and close-out.
17. `migrate-review-topology.py` remains the single explicit Beads mutation owner for graph migration. A new topology
    version creates both close reviewers, maps old close evidence without transferring approval, verifies the graph, and
    fails closed on busy lease, snapshot race, or failed verification.
18. Runtime formula and live graph mutation occur only from the canonical primary worktree under the Beads lease.
    Feature worktrees do not pretend to own `.beads`.
19. No lifecycle skill automatically runs an entire repository suite. Task checks and close-out checks remain focused.
20. The packet collector provider and packet-specific regression suite are retired. Their removal is itself a bounded
    implementation task; no regression tests are added for the removed packet behavior.

### Review State Transitions

The finite transition table remains unchanged except for source-boundary binding:

| Current state             | Event                                     | Next state                | Accounting                                               |
|---------------------------|-------------------------------------------|---------------------------|----------------------------------------------------------|
| `initial_active`          | `approve`                                 | provisional `approved`    | Initial pass completes only with no findings or decision |
| `initial_active`          | `findings`                                | `changes_required`        | Initial pass completes                                   |
| `initial_active`          | unresolved intent                         | `decision_required`       | Initial pass suspends                                    |
| `initial_active`          | timeout/unavailable                       | `initial_incomplete`      | Infrastructure counter unchanged                         |
| `initial_incomplete`      | explicit retry with counter = 0           | `initial_active`          | Same-pass counter becomes 1                              |
| `initial_incomplete`      | retry unavailable/declined or counter = 1 | `redesign_required`       | Terminal                                                 |
| decision/findings state   | all pending answer/fixes persisted        | `verification_active`     | Verification starts                                      |
| `verification_active`     | approve                                   | `approved`                | Verification completes                                   |
| `verification_active`     | eligible non-material findings            | `waiver_required`         | Verification completes without approval                  |
| `verification_active`     | material/protected finding                | `redesign_required`       | Terminal                                                 |
| `verification_active`     | timeout/unavailable                       | `verification_incomplete` | Infrastructure counter unchanged                         |
| `verification_incomplete` | explicit retry with counter = 0           | `verification_active`     | Same-pass counter becomes 1                              |
| `verification_incomplete` | retry unavailable/declined or counter = 1 | `redesign_required`       | Terminal                                                 |
| `waiver_required`         | user accepts eligible findings            | `approved_with_waiver`    | Terminal approval with ledger evidence                   |
| `waiver_required`         | user refuses/protected finding            | `redesign_required`       | Terminal                                                 |

A material redesign invalidates the old source boundary and review run. It requires a committed design/documentation /
validation boundary before one bounded redesign transition creates the next initial pass. A redesign never launches a
third reviewer against the old boundary.

## Architecture and Interfaces

The redesigned external seam is the controller-to-reviewer assignment, not a packet builder. The controller has one
small responsibility: derive and launch a bounded role assignment from Beads/design/Git authority, then persist the
result. Reviewers share one runtime interface but have different role prompts and declared evidence scopes. State and
aggregate providers remain pure and testable; Beads mutation and reviewer launch remain controller responsibilities.

The deletion test for `build-review-packet.py` is satisfied: deleting it removes the serialization bottleneck rather
than spreading packet assembly across callers. The controller's assignment derivation remains local to each workflow and
does not become a new durable manifest.

## Compatibility and Migration

Old packet/projection state may remain readable as append-only historical evidence during migration, but new executable
states use the source-boundary contract. Old packet-bound decisions do not authorize a redesigned boundary. Existing
installed reviewer assets update only through explicit synchronization. The old holistic gate is preserved as historical
mapping and superseded when the two new close gates are created.

The new topology version maps old review kinds as follows:

- old architecture, simplicity, and documentation evidence maps to specification-clarity history;
- old execution evidence maps to execution-readiness history;
- old delivery and drift evidence maps to delivery-integrity history; and
- implementation-integrity starts without transferred approval because no old role had that exact contract.

## Documentation Impact

| Concern                | Exact page/file                                                                                  | Change                                                                              | Owning task                  |
|------------------------|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|------------------------------|
| Architecture           | `docs/src/architecture/index.md`                                                                 | Replace packet/collector authority with Beads-backed direct assignments             | direct-review orchestration  |
| Operations             | `docs/src/operations/index.md`                                                                   | Document independent specialist launch, replacement, and close recovery             | direct-review orchestration  |
| Development            | `docs/src/development/feature-lifecycle.md`                                                      | Document direct role assignments and two close reviewers                            | direct-review orchestration  |
| Reference              | `docs/src/reference/index.md`                                                                    | Replace packet contract with source-bound review assignment contract                | review-authority             |
| Root policy            | `AGENTS.md`                                                                                      | State Beads-manifest authority and specialized roles                                | direct-review orchestration  |
| Generated policy       | `skills/setup-project/template/AGENTS.md.jinja`                                                  | Keep generated projects aligned                                                     | direct-review orchestration  |
| Generated lifecycle    | `skills/setup-project/template/docs/src/development/feature-lifecycle.md.jinja`                  | Keep generated lifecycle aligned                                                    | direct-review orchestration  |
| Reviewer roster/assets | `skills/dstack-core/references/PI-REVIEWER-ROSTER.md`, `skills/dstack-core/assets/pi-reviewers/` | Add implementation/delivery roles and remove obsolete holistic/collector references | reviewer-specialization      |
| Formula                | `.beads/formulas/dstack-feature.formula.toml`                                                    | Require two close reviewer gates                                                    | topology-migration           |
| Implemented record     | `docs/src/features/improve-workflow-reviews/index.md`                                            | Final pre-delivery status and packet-era audit reconciliation                       | documentation-reconciliation |
| Roadmap                | `docs/src/planned-features.md`                                                                   | Final pre-delivery status reconciliation                                            | documentation-reconciliation |

The documentation-reconciliation task verifies the behavior pages owned by the earlier tasks; it owns only final status,
audit, terminology, and navigation reconciliation. Behavior changes return to the owning task instead of being repeated.

## Validation Strategy

Focused validation includes:

- `tests/test_review_state.py` for source-boundary transitions, counters, decisions, waivers, and aggregate
  invalidation;
- reviewer asset tests for exact roles, runtime metadata, capabilities, and explicit synchronization;
- topology migration tests for the two-close-gate graph, old evidence mapping, idempotency, rollback, and no approval
  transfer;
- targeted repository-contract tests for direct controller orchestration and generated guidance;
- focused task checks for each redesign child; and
- `uv run --no-project python scripts/check-docs.py` when documentation changes.

The packet-construction tests and packet-specific validation are retired with the packet provider. No full repository
suite is an automatic lifecycle gate.

## Implementation Decomposition

The redesign is implemented as a new bounded sequence beneath a reopened implementation coordinator:

1. **Review authority:** simplify review state and aggregate contracts around Beads issue IDs and immutable Git source
   boundaries; remove packet/projection binding from new executable state.
2. **Reviewer specialization:** add direct clarity, readiness, task, implementation-integrity, and delivery-integrity
   definitions with explicit purposes, non-goals, domains, and report contracts.
3. **Direct orchestration:** update start, task, feature implementation, and close skills to derive role assignments
   from Beads and launch reviewers directly; remove collector/packet construction and packet-specific persistence.
4. **Topology migration:** update the formula, migrator, root metadata, dependencies, and generated graph to require two
   close reviewers and preserve old topology as superseded history.
5. **Retire packet provider:** remove `build-review-packet.py`, packet tests, packet references, and obsolete packet
   acceptance criteria without adding regression tests for removed behavior.
6. **Documentation reconciliation:** update architecture, operations, lifecycle, reference, root/generated policy,
   roadmap, implemented record, and synchronization guidance.
7. **Focused validation:** run the exact redesign child checks, docs checks, and a final focused contract selection;
   then create the new review boundary and launch the two direct close reviewers concurrently.

Every child has one owner, one bounded outcome, exact documentation ownership, focused validation, and a practical
commit boundary. The new implementation coordinator cannot close until the two close review beads and current validation
record are ready for the controller.

## Dependencies and Parallelism

Specification clarity and execution readiness remain independent start reviews and may run concurrently. The two close
reviewers are also independent and may run concurrently after documentation reconciliation and validation. Task review
remains one reviewer for one selected issue. State transitions, Beads mutations, topology migration, and shared
source-boundary reconciliation remain controller-owned serialized operations under the repository lease. The dependent
`parallel-feature-execution` feature owns implementation-worker parallelism.

## Rollout and Recovery

1. Commit the redesigned design and graph while the old close review remains explicitly non-approving history.
2. Reopen specification reconciliation and review the redesigned boundary with clarity and readiness reviewers.
3. Implement the provider, role, orchestration, migration, and documentation children in dependency order.
4. Install the reviewed local reviewer assets, start a fresh controller session, and verify the installed boundary.
5. Run the topology migration from the canonical primary worktree under the repository lease.
6. Reconcile docs and focused validation, create a new source-bound review boundary, and launch implementation/delivery
   reviewers concurrently.
7. Stop on any missing specialist, stale source boundary, incomplete evidence, unresolved finding, or aggregate failure.
   No PR, merge, push, `ready`, or Beads closure occurs before both close reviewers approve and the controller's
   structural aggregate check returns `can_close: true`.

## Risks and Tradeoffs

- Direct reviewers independently collect evidence, so prompts must be precise enough to prevent scope drift.
- Beads remains a live database rather than a frozen content bundle; source-boundary checks and clean read-only
  worktrees are therefore mandatory.
- Specialists may report overlapping findings; stable finding IDs and controller aggregation resolve duplicates without
  a collector.
- Close-out now requires two reviewers, increasing reviewer count but reducing overloaded review scope and serial
  failure coupling.
- A reviewer cannot see another reviewer's report during its pass; cross-role conflicts are resolved by the controller
  after both reports are persisted.

## Rejected Alternatives

- **Shared collector plus role projections:** rejected because it serialized evidence collection, duplicated source
  context, created a second authority layer, and made one collector failure block every specialist.
- **A single overloaded holistic reviewer:** rejected because implementation correctness and delivery reconciliation
  have different evidence, ownership, and failure modes.
- **A second durable review manifest:** rejected because Beads already owns the workflow manifest and acceptance data.
- **Larger packet/input limits:** rejected because limits would hide the wrong abstraction rather than remove the
  serialization bottleneck.
- **Automatic full suites:** rejected in favor of focused task/feature evidence.
- **Parallel implementation workers in this feature:** rejected; they belong to `parallel-feature-execution`.

## Historical Boundary and Audit

The earlier packet-based design and implementation are retained in Git and Beads history. Historical close reviews,
findings, packet identities, and transport failures remain attributable evidence and never imply approval for the new
boundary. The v14 close review identified aggregate changed-boundary reconciliation and reproducible validation gaps;
the attempted v15 rebuild then exposed the collector's input/serialization bottleneck and did not produce approval. The
redesign addresses the underlying architecture rather than adding another packet workaround.

The original specification, topology migration, focused-validation, and packet implementation commits remain audit
history. The redesigned design commit and subsequent implementation commits become the new source boundary for the next
bounded review. The implemented record remains pre-delivery until explicit delivery is authorized.

## Open Questions

None. The reviewer roles, authority split, close topology, source-boundary contract, migration policy, and validation
strategy are decided by this redesign.

## Deferred Decisions

- Workflow-level reviewer-budget overrides may be added if canonical defaults prove insufficient.
- Parallel implementation execution remains owned by `parallel-feature-execution`.

## Planning Record

### Questions Asked and Answers

- **What reviewer limits apply?** A 600,000 ms whole-run deadline, fresh isolated context, read-only acceptance, and
  persisted session/output completion evidence.
- **Should workflow overrides be implemented now?** No; defer them.
- **How should convergence findings be resolved?** Use finite bounded review lifecycles and return material scope
  changes to redesign rather than adding passes.
- **Which feature keeps the identity?** `improve-workflow-reviews` owns bounded review lifecycle and migration;
  `parallel-feature-execution` remains dependent.
- **How should self-migration work?** Install reviewed local skills, start a fresh controller, migrate from the
  canonical primary worktree, and close under the new topology.
- **Should a collector build shared packets?** No. Beads is the manifest; the controller launches targeted reviewers
  directly.
- **Which close roles are required?** `implementation-integrity` reviews correct code behavior, quality and simplicity,
  security, maintainability; `delivery-integrity` reviews documentation, validation, Beads state, implemented record,
  roadmap/navigation, delivery claims, and drift.

### Design Changes During Planning

The original combined feature included parallel workers and was split after review. The first delivered review topology
then used deterministic packets and a single holistic close reviewer. Close-out dogfooding showed that packet collection
serialized independent reviewers, duplicated evidence, and made collector failure a lifecycle bottleneck. This redesign
replaces that architecture with direct role assignments from Beads and two specialized close reviewers.

### Assumptions

- The installed reviewer runtime enforces the declared read-only capabilities and whole-run deadline; missing
  enforcement fails launch.
- The authoritative reviewed worktree is pinned and read-only for reviewers.
- User waiver authority never overrides protected correctness or safety domains.
- Beads issue content and append-only records remain available to the controller under the repository lease.

### Source Material

- User decisions from planning and redesign sessions.
- Prior specification review packets and recorded findings/resolutions.
- `skills/start-feature/SKILL.md`
- `skills/implement-feature/SKILL.md`
- `skills/implement-task/SKILL.md`
- `skills/close-feature/SKILL.md`
- `skills/dstack-core/references/REVIEW-STATE.md`
- `skills/dstack-core/references/REVIEW-FINDINGS.md`
- `skills/dstack-core/references/PI-REVIEWER-ROSTER.md`
- `skills/dstack-core/references/INTERACTION-BOUNDARY.md`
- `.beads/formulas/dstack-feature.formula.toml`
- `tests/test_repository.py`
- `tests/test_pi_reviewer_assets.py`
