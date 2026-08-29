# Harden workflow authority and auditability

> **Historical record:** setup/migration behavior described below reflects the workflow at the time this feature was
> delivered. It is superseded by the current
> [compatibility and formula-audit contract](../../reference/compatibility.md): formulas are templates, historical
> graphs are not migrated, and formula-contract drift is handled by semantic audit.

Status: planned

## Feature summary

dStack will become safe for unattended agent execution without changing its conceptual architecture. Beads remains
authoritative for operational work, dependencies, gates, readiness, claims, and completion. Git remains authoritative
for source, configuration, tests, durable documentation, implementation history, and delivery. `dstackctl` remains a
stateless adapter that invokes and verifies native operations; agents retain product and engineering judgment.

The release is ordered by risk:

1. restore native lifecycle authority and fail-closed authorization;
2. make durable documentation semantically enforceable and auditable; and
3. harden setup, diagnostics, compatibility evidence, and mechanical quality checks.

Unattended operation is not supported until the first group passes the real Beads acceptance boundary.

## User intent

The workflow already has the right authority split and must not be replaced by a larger orchestration framework. The
required outcome is to remove the controller paths that bypass or incompletely prove that split, then complete the
durable operator and auditor evidence chain without adding another task graph, state store, or workflow ledger.

The current architectural constraints are defined in the [architecture](../../architecture/index.md),
[development principles](../../development/index.md), and [workflow reference](../../development/feature-lifecycle.md).
This feature strengthens those contracts rather than superseding them.

## Goals

- An open task can be claimed for completion only through Beads-native readiness, and the claimed identity must be the
  requested identity.
- Feature authorization is valid only when the exact native specification, human gate, approval milestone, registered
  feature worktree, committed design blob, and accepted digest agree.
- Approved feature and alignment graphs cannot expand without a new explicit authorization boundary.
- Feature and alignment roots remain open after terminal reconciliation and close only after confirmed delivery.
- PR gates, ownership, worktree cleanliness, commit evidence, refs, and retry behavior fail closed on ambiguity.
- Feature and alignment records have deterministic semantic contracts while human review remains responsible for
  correctness and quality.
- Operators can install, configure, use, deliver, upgrade, recover, secure, and audit dStack from the canonical mdBook.
- Auditors can derive the current evidence chain from Beads, Git, and docs without persisting a joined workflow
  snapshot.
- Setup, doctor, compatibility shims, and CI expose the supported boundary and actionable recovery information.

## Non-goals

- Replacing Beads, Git, mdBook, GitHub gates, or Pi skills.
- Adding a dStack database, daemon, scheduler, queue, dependency graph, ready calculation, ownership ledger, reviewer
  topology, CI/PR poller, packet protocol, persistent audit cache, or approved-task manifest.
- Storing Git commit hashes in Beads or Beads IDs, gate IDs, current assignees, branches, commits, next commands, or
  transient lifecycle state in durable documentation.
- Recalculating blockers in Python or treating a simulated Beads client as proof of native behavior.
- Subjective prose scoring, an LLM-only documentation gate, a coverage percentage gate, or a finite review counter.
- Broad module splitting, repository-wide typing, or abstractions added only for file-size, style, or hypothetical
  future flexibility.
- Silent repair or rewriting of historical workflow topology during normal commands.

## User-visible behavior

### Work claiming and completion

For feature and alignment tasks, `claim-next --task` and `finish-task --task` share one exact-task transition policy:

- an open task is claimed only through the parent's native ready-and-claim query;
- the returned set must contain exactly the requested task;
- an already claimed or in-progress task is re-claimed natively so Beads verifies current ownership;
- a closed task is handled idempotently without a new claim; and
- blocked, non-owned, wrong-parent, wrong-label, or unexpected native results fail before closure.

Every completion path requires a completely clean worktree, including untracked files. Repository-changing work also
requires reachable `Beads: <id>` footer evidence. A no-repository-change completion requires a specific reason and no
reachable footer evidence. No generated-file allowlist is introduced until a real generated artifact demonstrates the
need.

A feature implementation workstream or alignment corrections workstream can close only after its authorization milestone
is closed and every direct child is terminal. This explicitly supports an authorized zero-work outcome while rejecting
premature closure.

### Feature authorization

Feature approval requires the exact registered conventional feature worktree. The design must be tracked, committed,
byte-identical to `HEAD`, and the worktree must be clean. The digest is calculated from the Git blob at
`HEAD:<design-path>`, not from a mutable filesystem read.

The controller resolves the human gate only through the approval milestone's native blocking dependency. A parent-level
gate listing may be used to hydrate that same identified dependency, but a sole unrelated gate is never accepted.

Approval converges in this order:

1. preflight root, specification, approval, gate, worktree, and committed design;
2. close or verify the specification;
3. resolve or verify the exact human gate;
4. close or verify the approval milestone;
5. re-read and verify all native states;
6. write the accepted design digest last; and
7. re-read the root and verify the final digest and all native states.

A partial failure may leave native states advanced, but implementation remains unauthorized until the digest is written
last and the complete read-side predicate agrees. Fault injection must prove that property after every external
mutation.

Read-only inspection reports `worktree_missing` or `design_state_unknown` when identity cannot be established. Mutating
commands never substitute the primary worktree or another branch.

### Approved scope and reauthorization

`feature add-task` and `alignment add-correction` reject new children after the corresponding authorization milestone
closes or the workstream closes.

The explicit reauthorization operation invalidates the accepted digest first, then uses native Beads transitions to
reopen the exact specification or analysis, human gate, and approval milestone. It verifies that the original dependency
relation still blocks implementation before allowing graph changes. Real Beads acceptance determines whether the pinned
release safely supports that transition. If it does not, dStack fails without mutation and requires a new planned
feature or alignment that natively supersedes the old workflow. It never stores an approved-task list.

### Terminal roots and delivery gates

One compatibility helper preserves both feature and alignment roots after their terminal reconciliation steps. It
reopens only a root automatically closed by the pinned Beads `all steps complete` behavior. Other closed states are not
rewritten. The helper is isolated, covered by a real Beads reproducer, and has an explicit retirement condition.

PR registration classifies all root-associated `gh:pr` gates before mutation:

- zero gates: create one;
- one open or closed gate for the same PR: return it idempotently;
- one gate for another PR: report a conflict;
- duplicate or multiple gates: report ambiguity; and
- a closed gate whose target branch does not contain the candidate: fail finalization.

An explicit cancel/replace command uses native gate/issue operations, records a reason, and creates a replacement only
after the old gate no longer authorizes delivery. Registration never creates a second gate as an ambiguity repair.

### Documentation, diagnostics, and audit

Design and reconciliation records are validated against fixed required sections. Each required subject contains
substantive content or exactly `Not applicable — <specific reason>`. Unresolved placeholders and TODOs fail. The parser
supports the repository's fixed ATX-heading contract and masks fenced and inline code. Contract records must use inline
Markdown links for local surfaces; unsupported local reference-style, HTML, and autolink forms are rejected mechanically
rather than interpreted heuristically.

Alignment workflows gain required durable plan and reconciliation records. The records explain evidence, findings,
decisions, delivered corrections, validation, limitations, and residual risk without copying operational state.

`dstackctl audit feature <selector> --format json|markdown` derives an audit view from current Beads, Git, and mdBook
data. It writes only to standard output unless the caller redirects it and creates no audit state.

Setup gains a deterministic read-only plan and an apply operation that repeats preflight before mutation. Doctor reports
exact supported tools, formulas, docs, interaction-log policy, worktree anomalies, Git/GitHub prerequisites, and known
migration or reconciliation gaps with actionable diagnostics.

## Requirements

### Native lifecycle authority

- Introduce one shared exact-task claim helper used by feature and alignment claim and finish commands.
- Validate parent and required work label before any claim.
- For open work, invoke Beads' ready-and-claim operation and verify the exact requested identity. Never query readiness
  and then perform a generic claim as two separate authorization steps.
- For already claimed work, use a native claim attempt as the ownership check.
- A blocked task must fail without mutation in real Beads tests.
- Require approval before workstream closure and preserve native dynamic-child fan-in plus the isolated direct-child
  compatibility guard.
- Require complete cleanliness and the correct footer/no-change evidence before closing every work task.

### Authorization integrity

- Bind approval to the committed candidate design blob and exact registered worktree.
- Require the exact native human-gate blocking relation.
- Write the digest only after native approval states converge.
- Make the read-side approved predicate include all native states, worktree identity, committed blob equality, and
  digest equality.
- Add fault-injection coverage after every approval mutation.
- Freeze feature and alignment scope after authorization and provide the tested native reauthorization-or-supersession
  behavior described above.

### Git and delivery integrity

- Keep both terminal roots open until confirmed delivery through one shared compatibility primitive.
- Model PR gate states explicitly and provide conflict-safe native replacement.
- Validate every externally supplied ref with `git check-ref-format` or the appropriate native revision check before
  use; pass option terminators where supported.
- Validate branch, worktree, base ancestry, and conventional placement before mutation. Clean up internally created
  branches/worktrees when post-creation verification fails.
- Preserve fast-forward-only delivery, complete candidate/target cleanliness, rewrite-safe footers, and the
  no-post-delivery-Git-mutation invariant.

### Semantic documentation contracts

Feature design records must address:

- intent and measurable acceptance;
- user/operator effects;
- configuration and defaults;
- deployment, migration, rollback, and recovery;
- architecture, interfaces, and data flow;
- invalid input and failure behavior;
- security and trust boundaries;
- compatibility;
- validation plan;
- documentation impact by audience;
- decisions and rationale;
- rejected alternatives; and
- deferred decisions with ownership.

Feature reconciliation records must address:

- delivered capability and deviations from accepted design;
- final architecture;
- operator, configuration, deployment, migration, and deprecation effects;
- links to current-product documentation;
- exact validation commands, environment/tool versions where material, observed results, date, omissions, and stable
  evidence links when available;
- limitations and untested conditions;
- remaining risks;
- decisions changed during implementation; and
- follow-up obligations without live workflow state.

Alignment plan and reconciliation records use the same applicability and placeholder rules for their audit-specific
subjects. The validator proves structure, explicit applicability, supported links, and absence of placeholders; human
approval and closeout review judge whether the prose is true and sufficient.

### Current-product documentation

The implementation adds only pages that answer demonstrated reader questions:

- `docs/src/operations/index.md`: install, upgrade, uninstall, configuration, defaults, daily use, worktrees, cleanup,
  and concurrency;
- `docs/src/operations/delivery.md`: direct merge versus PR authority, remote topology, GitHub authentication and
  permissions, retries, and finalization;
- `docs/src/operations/recovery.md`: setup and delivery partial failures, rollback, backup/restore, Beads/Dolt
  synchronization, troubleshooting, and common errors;
- `docs/src/security/index.md`: trust boundaries, repository and Beads instruction surfaces, subprocess privileges,
  force operations, confirmation boundaries, audit privacy, redaction, and secrets policy;
- `docs/src/reference/cli.md`: current command contracts;
- `docs/src/reference/environment.md`: environment variables and defaults;
- `docs/src/reference/metadata-labels.md`: stable metadata and label meanings; and
- the existing [compatibility reference](../../reference/compatibility.md): exact Beads and mdBook versions, mismatch
  recovery, upgrade policy, shims, and retirement conditions.

The [documentation guide](../../development/documentation.md),
[workflow reference](../../development/feature-lifecycle.md), and [testing guide](../../development/tooling.md) are
updated with semantic contracts, state-transition and native-operation tables, retry behavior, validation evidence,
error taxonomy, and release checks.

A `docs/src/decisions/index.md` explains ADR status and supersession. Initial ADRs are limited to demonstrated
cross-feature decisions: authority ownership, one-way Git evidence, committed-content approval,
root-open-until-delivery, and interaction-log/durable-documentation policy. Architecture pages continue to state current
truth; ADRs explain durable reasons and consequences.

### Setup, doctor, compatibility, and quality

- Setup plan output lists exact filesystem, Git-index, Beads, and docs changes derived from current truth and persists
  nothing.
- Apply repeats cleanliness/version/invariant preflight, uses atomic file writes, and compensates internally created
  objects where possible. Irreversible or uncertain partial failures report observed facts and recovery commands without
  claiming rollback.
- Doctor verifies exact Beads build, mdBook 0.5.3, formula identity/validity, documentation, interaction-log policy,
  missing reconciliations, worktree anomalies, tracked runtime paths, remotes, and GitHub prerequisites.
- Every compatibility shim has a pinned-version reproducer, smallest compensating behavior, upstream reference when
  available, and retirement condition. The like-kind dependency claim and dynamic-child fan-in shim are retained only if
  real Beads 1.2.2 proves them.
- CI explicitly uses Python 3.13 and adds Ruff, focused static typing of boundary data, coverage reporting without a
  threshold, dependency auditing, ref and CLI help tests, approval fault injection, PR-gate conflict tests, setup
  recovery tests, and the existing separated real-Beads scenarios.
- Commit guidance requires meaningful Conventional Commit subjects and bodies for controller, formula,
  documentation-policy, and compatibility changes while retaining `Beads:` work footers.

## Existing patterns and reuse

The design reuses existing code instead of adding parallel mechanisms:

- `BeadsClient.ready_children(..., claim=True)` remains the native atomic claim seam.
- The stable-step claim helper and direct-child fan-in guard are extended rather than replaced.
- `feature_branch_context`, Git worktree porcelain parsing, clean-worktree checks, footer evidence, ancestry, and
  delivery snapshots remain Git authority seams.
- `human_gate_for_step` remains the identity seam but loses the unrelated-gate fallback.
- `safe_design_file`, canonical feature paths, scaffold creation, code masking, link/include containment, `SUMMARY.md`
  reachability, and real `mdbook build` remain documentation seams.
- Existing feature design/reconciliation scaffolds become explicit contracts; no second schema or manifest file is
  introduced.
- Existing setup inspection and compatibility modules provide the plan/apply and shim registry seams.
- Fast scripted protocol tests remain useful for dStack decisions, while isolated real-Beads tests remain authoritative
  for native behavior.

New shared helpers are justified only where both feature and alignment paths must enforce one invariant: exact-task
claim, terminal-root preservation, ref validation, record-contract validation, and PR-gate classification.

## Proposed design

### Exact task transition

The shared transition accepts the native parent, required label, requested task, and transition name. It validates
identity before mutation. For open tasks it performs one `ready_children(parent, label, claim=True)` call and accepts
only an exact singleton result. For claimed tasks it repeats the native claim to let Beads enforce ownership. It never
closes the task; completion checks Git state and evidence before the separate native close.

This design intentionally does not compute blocker state or infer ownership in Python.

### Approved feature context

Approved context becomes a strict conjunction:

```text
current molecule
AND specification closed
AND exact human gate closed
AND approval milestone closed
AND registered conventional feature worktree exists
AND design is tracked at candidate HEAD
AND clean worktree bytes equal HEAD blob
AND stored digest equals HEAD blob digest
```

Inspection returns the individual observations. Mutation helpers require the conjunction. Approval writes the digest
last, so every earlier partial state is non-authorizing.

### Scope freeze

Graph creation preflights native authorization and workstream states. The reauthorization command invalidates
authorization before reopening any native boundary. It verifies the original dependency graph after reopening. If the
pinned native behavior cannot restore the gate as a blocker, the command aborts and directs the user to a new natively
superseding workflow.

### Documentation contracts

Contracts are Python constants defining ordered required subject names and applicability rules, not persisted state. The
validator parses supported ATX headings after masking code, normalizes heading text, rejects duplicates and
placeholders, and validates each required section body. It accepts a substantive body or a specific
`Not applicable — ...` reason. Links continue through the existing containment checker; unsupported local link syntaxes
are rejected.

Scaffolds and validators share the same constants so templates cannot drift from the enforced contract.

### Stateless audit view

The audit command resolves the current feature and derives:

1. root intent and stable lifecycle identities from Beads;
2. exact approval dependency and native history/state;
3. accepted and current committed design digests from Git and Beads;
4. implementation children and native dependencies from Beads;
5. reachable footer evidence and changed paths from Git;
6. current documentation links, design, and reconciliation from mdBook;
7. validation evidence and stated limitations from the reconciliation record;
8. direct or PR delivery observations from Git/GitHub gates; and
9. related ADRs from local document links.

JSON uses stable named fields with explicit `unknown` or missing observations. Markdown is a deterministic rendering of
the same in-memory result. Neither format is checked in or written back to Beads.

### Setup plan/apply

Plan and apply call the same stateless discovery function. Plan emits intended changes only. Apply repeats discovery
after full preflight, performs the minimum native mutations, verifies each postcondition, and emits both completed and
remaining recovery facts on failure. No transaction journal is added.

## Architecture consistency

The design preserves the one-authority-per-concern table in the
[development principles](../../development/index.md):

| Concern | Authority | dStack behavior |
|---|---|---|
| Work graph, blockers, gates, readiness, claim, completion | Beads | Invoke native operations and verify exact postconditions |
| Source, tests, docs, committed design bytes, history, delivery | Git | Inspect and enforce repository invariants |
| Accepted product and architecture specification | Repository docs | Validate deterministic record contracts |
| Mechanical orchestration | Stateless `dstackctl` | Recompute current truth every invocation |
| Product and engineering judgment | Human and agents | Approve meaning, tradeoffs, and residual risk |

No proposed command persists derived readiness, approval membership, audit joins, setup plans, or Git-to-Beads mappings.

## Interfaces and data flow

### Task completion

```text
requested task
  -> Beads show/parent/label validation
  -> native ready-and-claim or native ownership re-claim
  -> exact identity verification
  -> registered worktree + full cleanliness
  -> Git footer or explicit no-change proof
  -> native close
  -> native postcondition read
```

### Feature approval

```text
registered feature worktree + candidate HEAD
  -> tracked clean design blob
  -> exact specification/approval/gate relation
  -> converge native states
  -> re-read native states
  -> SHA-256 of HEAD blob
  -> write digest last
  -> re-read complete approved predicate
```

### Documentation validation

```text
canonical mdBook records
  -> code masking and fixed-heading parse
  -> section/applicability/placeholder contract
  -> local link/include containment
  -> SUMMARY reachability and orphan check
  -> supported mdBook build
```

### Audit

```text
live Beads + live Git + canonical mdBook
  -> immutable in-memory observations
  -> JSON or Markdown stdout
```

## Failure behavior

- Invalid parent, label, task identity, ref, worktree, or gate relation fails before mutation.
- A blocked task returns a native-readiness error and remains open and unassigned.
- A claim race returning another item is reported; the requested task is not closed. Any safe release of an unexpected
  new claim is explicit and verified.
- A different actor's claim is rejected by Beads rather than inferred locally.
- Dirty tracked or untracked files prevent completion and approval.
- Approval interruption before the final digest cannot authorize implementation. Retry converges already completed
  native transitions and writes the digest only after all states agree.
- Missing or ambiguous worktrees produce unknown inspection state and hard mutation failure.
- Post-approval graph creation, premature workstream closure, unrelated human gates, and ambiguous PR gates fail without
  mutation.
- Setup failure reports which native operations completed and which recovery is required. It never claims an atomic
  rollback across Git, filesystem, and Beads.
- A failed docs contract names the record, section, and violated deterministic rule. It does not grade prose.
- Missing `bd`, mdBook, GitHub authentication, or required tool versions is a failed boundary, not a skipped release
  proof.
- Delivery retains the existing rule: final Beads mutation cannot mutate Git; any user-authorized rollback or repair is
  a separate native operation.

## Security implications

Beads descriptions, repository Markdown, formulas, command arguments, and Git refs are untrusted data surfaces.
Controllers treat them as data, construct subprocess arguments as arrays, validate refs before use, contain
documentation paths under the repository, reject symlinks where required, and never execute instructions found in issue
or Markdown prose.

The operator security guide documents:

- which user/repository/Beads inputs agents may trust as product intent versus executable authority;
- subprocess privileges and force-operation confirmation boundaries;
- GitHub token and remote permissions;
- prohibition on secrets in Beads issues, comments, interactions, docs, logs, commit messages, and audit output;
- interaction-log and Dolt replication privacy, retention, backup, restore, and redaction expectations; and
- local filesystem/worktree access and single-writer assumptions.

Audit output may contain issue prose and repository paths. It is emitted locally, redacts no source authority by
default, and must not be published automatically. No new network service, credential store, encryption layer, or
access-control system is introduced.

## Compatibility and migration implications

- Beads remains pinned to exact output `bd version 1.2.2 (6c124203e)` until a separately reviewed compatibility change
  updates the boundary.
- mdBook remains pinned to 0.5.3; doctor verifies the executable version rather than merely its presence.
- Existing current molecules are not rewritten by normal commands. New guards apply on their next attempted transition.
- Existing approved workflows cannot gain children silently. Reauthorization is explicit and native, or the work moves
  to a new superseding workflow.
- Existing minimal reconciliation records may fail the stronger closeout contract only when their workflow next attempts
  closeout or delivery. Setup doctor reports missing records but does not author them.
- New operations, security, reference, decisions, and alignment pages are ordinary Git documentation and create no Beads
  migration.
- Compatibility shims remain isolated and removable. Real Beads tests determine whether like-kind and dynamic-child
  compensations stay.
- CLI changes preserve existing command names unless a new explicit reauthorization, gate-repair, setup-plan, or audit
  command is required.

## Validation strategy

Tests are written before each behavioral change and assert observable outcomes.

### Fast controller tests

- exact requested-task claims, wrong identity, wrong label/parent, ownership conflicts, and clean/no-change/footer
  boundaries for feature and alignment;
- approval preflight, committed blob hashing, exact gate relation, digest-last ordering, read-side conjunction, and
  fault injection after every mutation;
- post-approval graph rejection and reauthorization failure handling;
- root preservation and PR gate zero/match/conflict/duplicate/closed states;
- ref validation and worktree rollback;
- semantic record sections, applicability reasons, placeholders, supported links, alignment records, ADR
  status/supersession, and validation tables;
- audit JSON/Markdown equivalence and proof that execution writes no state;
- setup plan/apply retries, partial-failure reporting, doctor diagnostics, version mismatch, CLI help, and
  compatibility-shim behavior.

### Real Beads acceptance

Separate pinned-binary scenarios prove:

- blocked open feature and alignment tasks fail without mutation;
- exact native ready claims and ownership conflicts;
- gate dependency identity;
- reauthorization reopen behavior or the supersession fallback;
- feature and alignment roots remain open after terminal reconciliation and close only after delivery;
- same-PR retry, conflicting PR, duplicate gate, closed gate, and repair behavior;
- like-kind dependency and dynamic-child fan-in behavior.

Fast protocol tests never substitute for these results.

### Repository release checks

- supported mdBook validation and build;
- fast tests and each real-Beads acceptance scenario separately;
- Python compile and configuration parsing;
- Ruff and focused static typing;
- dependency audit and coverage report without a threshold;
- `git diff --check` and `git fsck`;
- bundle verification and clean-clone checks; and
- explicit Python 3.13 and pinned tool-version evidence.

Validation records list exact commands, material tool/environment versions, observed result, UTC date, omissions, and
stable CI/artifact links when available. Unavailable real boundaries are documented omissions and block release claims.

## Documentation impact

### End user and operator

- Usage and configuration: add the operations overview and `docs/src/reference/environment.md`; update the
  [workflow reference](../../development/feature-lifecycle.md).
- Deployment, upgrade, and rollback: add `docs/src/operations/delivery.md` and `docs/src/operations/recovery.md`; update
  the [compatibility reference](../../reference/compatibility.md).
- Operations, troubleshooting, and recovery: add `docs/src/operations/recovery.md`, `docs/src/security/index.md`, and
  exact CLI and metadata reference pages.

### Developer and reviewer

- Architecture and structure: update the [architecture](../../architecture/index.md) and add the decisions index and
  bounded cross-feature ADRs.
- Interfaces, contracts, and maintenance: update the [documentation guide](../../development/documentation.md),
  [workflow reference](../../development/feature-lifecycle.md), and [testing guide](../../development/tooling.md) with
  transition, native-operation, semantic-contract, compatibility, retry, and release-check details.

### Future auditor

- Decisions and rationale: retain this accepted design, add ADR supersession, and require durable alignment
  plan/reconciliation records.
- Invariants, regression evidence, and known limitations: require semantic reconciliation and validation tables,
  current-product links, real-boundary tests, and the stateless audit view.

No audience is `N/A`; all three are directly affected.

## Risks and tradeoffs

- The scope is large. Bounded outcome tasks and minimal real predecessor edges prevent a monolithic implementation while
  keeping one authorization boundary.
- Stronger guards can expose previously tolerated partial or ambiguous workflows. Diagnostics and explicit native repair
  are required; silent compatibility is not.
- Digest-last approval cannot make Beads and Git one transaction. It instead guarantees the safe direction: partial
  native progress does not authorize implementation.
- Native reauthorization may not be safe in the pinned Beads release. The accepted fallback is failure without mutation
  plus a natively superseding workflow, not custom state.
- Strict documentation contracts can encourage boilerplate. Specific not-applicable reasons and human review are
  preferred over word counts or scoring.
- New quality tools add maintenance cost. They are limited to well-known tools that enforce requested boundaries; no
  arbitrary coverage target is added.
- Audit output joins sensitive local facts. It remains local and read-only and is never auto-published.
- Setup cannot be globally transactional across external systems. Recomputed plans, preflight, atomic writes,
  compensation, and exact recovery facts are safer than a custom transaction ledger.

## Rejected alternatives

- A new workflow engine, scheduler, database, state cache, task manifest, audit ledger, or Git-to-Beads mapping.
- Python blocker calculation or direct claim as a substitute for native ready claim.
- Hashing mutable worktree bytes or writing the digest before native states converge.
- Accepting a sole root gate without proving its blocking dependency.
- Allowing post-approval graph changes because new tasks inherit a closed approval dependency.
- Persisting an approved task-ID set.
- Creating duplicate PR gates and repairing ambiguity later.
- Keeping feature-only root auto-close handling.
- Subjective or word-count documentation scoring.
- Using feature history as the current operator runbook.
- Checking in audit reports or setup plans.
- A broad typed rewrite, arbitrary coverage threshold, or file-size-driven module split.

## Open or intentionally deferred decisions

The accepted behavior is fixed; only evidence-driven implementation choices remain:

1. **Reauthorization primitive:** real Beads 1.2.2 acceptance owns whether exact gate/milestone reopen is safe. If not
   proven, the required behavior is fail-without-mutation and native supersession.
2. **Like-kind and dynamic fan-in shims:** pinned-binary reproducers decide whether each existing compatibility shim
   remains. An unproven claim is removed rather than documented as native fact.
3. **Focused typing boundary:** type only the workflow views and transition payloads whose ambiguity caused concrete
   defects. Do not broaden the feature into repository-wide model replacement.
4. **Stable external evidence links:** include CI or artifact URLs when retention is stable; the validation record must
   remain understandable without them.

No unresolved product, authority, security, or release decision remains for implementation authorization.
