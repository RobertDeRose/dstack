# dStack architecture

## System boundary

```text
User / Pi command
        |
        v
short decision-oriented skill
        |
        +---- agent makes engineering decisions
        |
        v
stateless dstackctl operation
        |
        +---- native bd commands ------> Beads / Dolt
        |
        +---- native git commands -----> Git repository
```

There is no dStack daemon, database, task store, scheduler, packet protocol, or workflow ledger. Repository content,
Beads records, formula source, Git refs, remote responses, and GitHub text cross trust boundaries into an adapter
running with the invoking user's privileges. Path containment, structured subprocess arguments, explicit authorization,
clean-worktree checks, native atomic claims, and postcondition verification constrain that boundary; the
[security guide](../security/index.md) defines secrets and audit-data policy.

## Components

### Beads

Beads owns planned feature intent, formulas, poured molecules, tasks, parent/child structure, dependencies, gates,
claims, readiness, completion, TODOs, decisions, and pending validation. dStack never calculates its own ready frontier.
Beads 1.2.2 can miss nonterminal dynamic children in `children-of(...)` fan-in, so dStack additionally refuses terminal
claim, closure, and delivery while any direct workstream child is nonterminal. Native `bd ready --claim` still owns
every other blocker and the atomic claim.

### Git

Git owns source, tests, configuration, durable documentation, branches, worktrees, diffs, commits, and delivery history.
Workflow commits use a stable `Beads: <id>` footer.

Beads repository configuration may also be tracked when it is stable project configuration (`.beads/config.yaml`,
`.beads/metadata.json`, `.beads/README.md`, `.beads/.gitignore`, and dStack formulas). Machine-local databases, locks,
sockets, backup state, and the dStack-local interaction audit log are not Git history. Delivery guards classify those
paths explicitly instead of treating every `.beads/` file as runtime state. Workflow commits created by
`dstackctl git commit` still exclude setup/configuration paths so feature history cannot accidentally absorb environment
setup; those stable files are reviewed and committed in a separate native Git setup boundary.

### Repository documentation

Documentation is the durable accepted product and architecture specification and description of product behavior. It is
materialized during repository-aware review and used by people and agents to detect drift between intent and
implementation. Unreviewed planned feature intent remains in Beads, so abandoned ideas create no Git artifacts.
Documentation is not an execution dashboard.

### `dstackctl`

`dstackctl` is a stateless deterministic adapter. It may:

- query and validate Beads JSON;
- resolve exact feature/audit selectors and stable steps;
- run idempotent native Beads transitions;
- initialize and validate the canonical mdBook foundation without storing a second navigation manifest or validation
  state;
- create/reuse conventional Git branches and worktrees;
- enforce Git footer, aggregate PR-summary, and delivery safety rules;
- compute a content digest for an approved design;
- perform narrow, explicit legacy adoption.

It may not:

- persist state outside Beads/Git;
- compute task readiness independently;
- invent lifecycle states;
- save inter-agent packets;
- cache a Git-to-Beads mapping;
- poll GitHub instead of using Beads gates.

Every invocation derives truth from the current repository and Beads database.
Mutation commands load only stable identity, metadata, and lifecycle steps, then
query the additional native state required for that operation. Full dashboard
hydration (gates, ready work, progress, and delivery state) is reserved for
inspection and delivery. Nested transitions reuse the invocation's Beads client;
no cache or state survives the process.

Compatibility is an explicit boundary: legacy adoption is dispatched only by
`adopt`, and repository repair is dispatched only by the explicit setup repair
operation. Normal feature, alignment, evidence, and delivery operations do not
run either path or rewrite historical workflow data. The isolated compatibility
module can be retired once supported repositories no longer contain active
legacy workflows.

### Pi skills

Skills are short policy and judgment guides. They tell the agent:

- what evidence to inspect;
- what decisions it must make;
- what authority the user granted;
- when to stop and ask;
- which deterministic command completes the mechanics.

Exact shell choreography belongs in `dstackctl --help` and tests, not repeated across skills.

## Minimal feature molecule

Before a molecule exists, `/plan-feature` preserves complete planned intent in a normal Beads feature epic without
changing Git. `/review-feature-spec` consumes that intent, materializes the canonical design and stable molecule, and
obtains human authorization.

```text
specification task
        |
        v
approval task <---- human gate
        |
        +----> dynamic implementation task
        +----> dynamic implementation task

implementation epic owns dynamic tasks
        |
        v
closeout waits for children-of(implementation)
```

The approval task exists because normal Beads blocking relationships must connect like issue kinds. The implementation
workstream remains an epic and the closeout uses native dynamic fan-in.

## Minimal project-alignment molecule

```text
analysis/plan task
        |
        v
approval task <---- human gate
        |
        +----> dynamic correction task
        +----> dynamic correction task

corrections epic owns dynamic tasks
        |
        v
landing waits for children-of(corrections)
```

The three authority tiers remain separate: analyze, execute, deliver.

## Minimal metadata

Feature root:

```text
labels:
  workflow:feature
  feature:<slug>
metadata:
  dstack.base_branch
  dstack.design_path
  dstack.pending_design_sha256    # only while approval is incomplete
  dstack.approved_design_sha256   # only after approval
```

Stable children carry one `dstack:step:*` label. Dynamic work carries one `dstack:work:*` label and is associated with
the feature through parentage. Conventional branch/worktree paths and supersession are derived from Git and the Beads
graph, not duplicated in metadata.

## Design approval without Git coupling

Specification approval stores a SHA-256 digest of the accepted design file content in namespaced Beads metadata. It does
not store a commit SHA and does not require an empty approval commit. Before any native authorization state closes,
dStack writes and verifies a pending content digest. After every native state converges it promotes that identity to
approved, verifies it, and clears pending.

Before implementation, dStack recomputes the digest from the feature worktree. Authorization requires matching committed
content, closed native specification, human gate, and approval states, an approved digest, and no pending digest. A
mismatch means the design changed and must be reviewed again. A rebase, cherry-pick, or commit-message rewrite does not
affect approval.

## Delivery invariant

Before delivery, all durable code/docs changes are already in the candidate. After delivery starts, Beads may be
finalized but Git may not change.

`dstackctl delivery` requires clean candidate and target worktrees, snapshots the target HEAD and full status including
untracked files, performs the native delivery/finalization operations, and reports any Git mutation caused by Beads
finalization with explicit delivered/recovery facts. It never rewrites delivered Git history or creates a post-delivery
bookkeeping commit.

This invariant governs normal delivery. An explicit user-authorized rollback,
reset, repair, correction, or history rewrite after a failed or incorrect
delivery is a separate native Git operation, not a dStack recovery lifecycle.
