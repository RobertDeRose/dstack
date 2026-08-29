# dStack core principles

These principles are architectural constraints, not suggestions. New workflow features must satisfy them before
implementation.

## KISS and YAGNI first

Use the smallest mechanism that preserves correctness and recoverability. Prefer an existing Beads or Git primitive over
a dStack abstraction. Do not add a service, database, packet format, lifecycle node, metadata field, or review state
merely because it might be useful later.

A proposal should answer both questions:

1. What demonstrated problem does this solve?
2. Why can Beads, Git, or a small stateless command not already solve it?

## Feature design quality contract

A feature design must make the following explicit:

- the user/developer outcome;
- non-goals;
- existing patterns and reuse;
- why any additional abstraction is necessary;
- observable behavior that proves success;
- failure, negative, security, and compatibility behavior;
- the validation strategy; and
- the documentation impact.

Prefer an existing pattern over a new abstraction. Add complexity only when a concrete requirement requires it. Do not
add scoring systems, design grades, approval matrices, or additional Beads metadata.

Tests prove externally meaningful behavior, invariants, failure handling, and regression boundaries. They should fail
when behavior is wrong, not merely confirm that the current implementation was executed. Review should consider
happy-path outcomes, invalid/input rejection, state-transition or persistence behavior, failure recovery, security
boundaries where relevant, and compatibility/regression behavior. Avoid tests tied to private methods solely to raise
coverage, assertions about implementation structure when behavior is what matters, and mocks that prevent the tested
behavior from occurring. Do not add a coverage-percentage gate.

Documentation impact considers three perspectives without requiring three documents:

- **End user/operator:** what users need to use, configure, troubleshoot, or understand the behavior;
- **Developer/reviewer:** where design constraints, interfaces, architecture, and maintenance expectations are
  documented; and
- **Future agent/auditor:** which durable docs and tests establish intent well enough to detect implementation drift
  later.

Each perspective may be `N/A` only with a reason. Future agents use the same durable architecture, design, user
documentation, tests, and Beads intent as people do; no separate agent documentation is required.

## Automate deterministic work

Mechanical work belongs in tested, idempotent commands. Examples include:

- resolving a feature and its stable molecule steps;
- creating or reusing a branch and worktree;
- claiming or closing native Beads work;
- validating a design-content digest;
- adding a `Beads: <id>` Git footer;
- checking delivery ancestry and remote-base freshness;
- resolving a gate and completing its milestone;
- using packaged dStack formula authority and checking semantic formula-contract versions.

Automation must remain stateless. It reads current truth from Beads and Git on every invocation and writes only through
their native interfaces. It must not cache readiness, duplicate dependencies, or create a dStack state store.

## Formula contracts are templates, not schemas

**Formulas define how dStack creates and reviews new work; they are not schemas that existing work must migrate to.** A
formula version is a semantic planning/review contract version. Package releases that do not materially change the
contract do not increment it.

The controller silently keeps installed dStack formulas current. Existing approved feature graphs retain their historical
labels, task grouping, and closed work. When an active feature was last audited under an older or unknown contract, the
controller requests an internal semantic specification audit. The review compares outcomes, acceptance, validation,
dependencies, failure behavior, and documentation expectations—not topology.

If the current approved work already covers the contract, dStack records the current audited version on the feature and
active work and continues. If a material gap exists, the agent proposes only the minimum delta and must obtain renewed
user approval before changing the approved design or execution graph. No setup command, repository migration, or bulk
historical normalization is part of an upgrade.

## Focus agent compute on decisions

Agent effort is reserved for work requiring judgment:

- architecture and implementation strategy;
- task decomposition and dependency decisions;
- code, tests, failure handling, security, and compatibility;
- durable user/developer documentation;
- review findings and product decisions.

The agent should not spend context remembering a sequence of bookkeeping commands or translating the same state between
tools.

## One authority per concern

| Concern | Authority |
|---|---|
| Work, planned feature intent, dependencies, gates, ready/blocked/closed state | Beads |
| Code, tests, configuration, durable docs, commit history | Git |
| Accepted product and architecture specification | Repository documentation |
| Mechanical orchestration | Stateless `dstackctl` commands |
| Engineering judgment and user interaction | Pi skills/agent |

No concern should have two writable sources of truth.

Stable Beads project configuration may be committed, but Beads runtime and audit churn must not become feature history.
dStack follows Beads' own runtime classification and additionally keeps `.beads/interactions.jsonl` local so state
transitions do not dirty the repository.

## Beads and Git are deliberately decoupled

Never store Git commit identities in Beads as implementation, delivery, task, evidence, or bookkeeping mappings. A
commit references its work item with:

```text
Beads: <bead-id>
```

This is a one-way, rewrite-safe link. Rebases, cherry-picks, and amended commit messages create new Git identities while
preserving the same Bead footer. Audit queries reconstruct the current relationship from reachable Git history; they do
not persist a SHA mapping back into Beads.

Alignment plans contain reviewed findings, accepted corrections, and user decisions. They do not store Git revisions or
repository snapshots. Each execution and delivery boundary revalidates the current repository and reconstructs work
evidence from reachable Git history. Beads may contain durable intent, acceptance criteria, decisions, validation still
required, and accepted risk, but must not become a duplicate Git log.

## Documentation is not workflow state

Documentation explains accepted product and architecture intent, what is planned or implemented, why it exists, how it
works, and which stable design constraints apply. Before specification review, sufficiently lossless planned feature
intent belongs to the feature Bead and creates no repository artifact.

Allowed durable product classifications include:

- planned;
- implemented;
- deprecated.

Forbidden transient workflow content includes:

- in-progress, review-active, blocked, or delivery-ready state;
- Beads IDs, gate IDs, branch names, or commit hashes;
- agent ownership or the next dStack command.

The accepted design is prepared before implementation; current-product documentation and the delivered reconciliation
belong to the final closeout or alignment landing. Implementation and correction tasks do not create documentation or
reconciliation work. During normal delivery, dStack may change Beads state after the Git update but may not mutate Git
or create a bookkeeping commit. Explicit user-authorized Git recovery after a failed or incorrect delivery is a separate
operation, not another lifecycle state.

## Comments are for irreducible evidence

Do not use Beads comments as another ledger. Persist a comment only when native state, dependencies, or Git cannot
express the information, such as:

- a user product decision;
- material unresolved review findings;
- accepted risk;
- validation deferred to another environment;
- a concise final review outcome when it carries durable evidence.

Successful routine transitions require no narrative comment.

## Review is evidence, not authority

A review finding is `changes requested` when it can be fixed inside accepted scope. It is `decision required` only when
accepted product or architecture intent must change. Reviewer failure is `review unavailable`, not a design result.
There is no finite review counter that can override explicit user authorization.

Use “independent review” only when a separate agent/session actually performed it. Otherwise call it a review.

## Test every real boundary

Fast unit tests may use a Beads test double. Release acceptance must also run the supported real `bd` binary when
available, including JSON envelope mode. A fake CLI must never be treated as the final authority for Beads behavior.
