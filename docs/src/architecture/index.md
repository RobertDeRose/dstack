# dStack architecture

## System boundary

```text
User / Pi command
        |
        v
short decision-oriented skill
        |
        +---- compact installed dStack system guidance
        +---- agent makes engineering decisions
        |
        v
installed `dstack ctl` operation
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
`.beads/metadata.json`, `.beads/README.md`, and `.beads/.gitignore`). Packaged dStack formulas remain package authority;
native pours expose them transiently and restore any historical project copy afterward. Machine-local databases, locks,
sockets, backup state, and the dStack-local interaction audit log are not Git history. Workflow commits created by
`dstack ctl git commit` exclude all `.beads/` paths so feature history cannot accidentally absorb Beads/controller
maintenance; intentional stable Beads configuration changes are separate repository maintenance.

### Repository documentation

Documentation is the durable accepted product and architecture specification and description of product behavior. It is
materialized during repository-aware review and used by people and agents to detect drift between intent and
implementation. Unreviewed planned feature intent remains in Beads, so abandoned ideas create no Git artifacts.
Documentation is not an execution dashboard.

### `dstack` CLI

`dstack` is an installable Python tool. `dstack ctl` is its stateless deterministic adapter. It may:

- query and validate Beads JSON;
- resolve exact feature selectors and stable steps;
- run idempotent native Beads transitions;
- initialize and validate the canonical mdBook foundation without storing a second navigation manifest or validation
  state;
- create/reuse conventional Git branches and worktrees;
- enforce Git footer, aggregate PR-summary, and delivery safety rules;
- compute a content digest for an approved design;

It may not:

- persist state outside Beads/Git;
- compute task readiness independently;
- invent lifecycle states;
- save inter-agent packets;
- cache a Git-to-Beads mapping;
- poll GitHub instead of using Beads gates.

Every invocation derives truth from the current repository and Beads database. `uv tool install` places `dstack` on
`PATH`; controller modules live in the installed Python package rather than under Pi skills. Before Beads-backed work,
the controller validates the supported Beads binary, initializes Beads when needed, and uses packaged dStack formulas as
authority. Formula source is exposed transiently for native pours; legacy tracked copies are tolerated and restored
unchanged. No setup or adoption workflow or migration authority exists.

Formula versions are semantic planning/review contracts. New feature roots record their creation version; approved
active features record the latest audited version. A stale/missing audited version does not override Beads readiness or
change the existing molecule. When the feature is explicitly reviewed under the current contract, the
specification-review skill owns the semantic decision; dStack emits no inter-agent packet and creates no compatibility
work item. If the existing design/tasks already satisfy current expectations, `feature audit-complete` stamps only the
root contract version. Material gaps reuse the existing specification/human-gate/approval boundary after explicit user
reauthorization.

**Formulas define how dStack creates and reviews new work; they are not schemas that existing work must migrate to.**
Historical labels, task groupings, and closed work are left intact. Current root resolution uses parentless topology,
root type, compatible identity, and the current workflow marker. Historical active graphs that do not contain the current
molecule remain native Beads records rather than controller-managed workflows. dStack neither migrates nor normalizes
them; users may complete them with native Beads or explicitly plan a new current feature. No compatibility database,
migration map, setup ledger, or historical normalization state is stored.

### Pi integration

`dstack install_skills` copies dStack's prompt templates and decision skills into Pi and maintains one dStack-owned
block in the global `APPEND_SYSTEM.md`. The former `dstack-beads-core` skill does not exist: stable CLI usage,
formula-compatibility guardrails, and cross-workflow guardrails are always available through that compact system-prompt
additive.

Skills are short policy and judgment guides. They tell the agent:

- what evidence to inspect;
- what decisions it must make;
- what authority the user granted;
- when to stop and ask;
- which deterministic command completes the mechanics.

Exact shell choreography belongs in `dstack ctl --help` and tests, not repeated across skills.

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

## Project audit

`/project-audit` is a read-only Pi command. The agent compares current source,
tests, Beads, Git, and governing documentation, then reports evidence-backed
contradictions, drift, and consequential ambiguity. It presents a proposed
corrective feature epic but creates no audit Bead, packet, ledger, or snapshot.

After explicit acceptance, the proposal becomes ordinary planned feature intent.
`/review-feature-spec` obtains authorization and `/implement-feature` handles its
implementation children; feature closeout reconciles durable documentation.

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

## Git identity boundary

Never store Git commit identities in Beads as implementation, delivery, task, evidence, or bookkeeping mappings. Those
relationships remain one-way `Beads: <id>` footers and are reconstructed from reachable Git history.

Project audits do not persist reviewed findings or repository snapshots in dStack state. Accepted corrective work is
represented by ordinary Beads feature intent and Git history, with evidence reconstructed at delivery boundaries.

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

Before delivery, all durable code/docs changes are already in the candidate. Feature closeout is the sole
reconciliation boundary; implementation tasks do not update durable documentation. A candidate may be
amended, fixed up, or rebased before delivery when its history remains linear and final terminal evidence stays
reachable. After delivery starts, Beads may be finalized but Git may not change.

`dstack ctl delivery` requires clean candidate and target worktrees, snapshots the target HEAD and full status including
untracked files, performs the native delivery/finalization operations, and reports any Git mutation caused by Beads
finalization with explicit delivered/recovery facts. It never rewrites delivered Git history or creates a post-delivery
bookkeeping commit.

This invariant governs normal delivery. An explicit user-authorized rollback, reset, repair, correction, or history
rewrite after a failed or incorrect delivery is a separate native Git operation, not a dStack recovery lifecycle.

### Immutable delivered-candidate audit

A closed feature inspection searches the configured target ref for the latest reachable closeout `Beads:` footer.
Sequential fixups and rebases are valid; repeated identical footers in one commit and nonlinear evidence remain errors.
Before delivery, the clean candidate HEAD must contain the final terminal footer and any later commits must retain that
terminal footer; this prevents unreviewed commits from silently extending the candidate while allowing fixups and
rebases.

Delivered evidence is read from the current target's reachable footer history. Feature audit documentation is read from
the derived candidate revision when one exists. Inspection reports the search ref, derivation rule, revision,
branch/worktree presence, evidence source, and missing records. It never stores a Git-to-Beads mapping in Beads; a
history rewrite that removes evidence is reported as unavailable rather than remapped.
