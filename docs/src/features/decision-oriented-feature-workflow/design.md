# Decision-oriented feature workflow

## Goal

Make each public feature command correspond to one engineering decision:

```text
/plan-feature          decide what to build and why
/review-feature-spec   reconcile that intent with the repository and authorize it
/implement-feature     implement only the authorized outcomes
/close-feature         reconcile intent, implementation, evidence, docs, and delivery
```

Planning preserves sufficiently lossless product intent in Beads without creating repository artifacts. Specification
review materializes that intent as the canonical repository-aware design and implementation graph. The redesign removes
`/start-feature` as both a public command and an internal agent methodology while retaining its deterministic
initialization mechanics in `dstackctl`.

## User-visible behavior

### Plan feature

`/plan-feature [id|slug|title|request]` conducts interactive design discovery. The agent:

- understands the requested outcome and why it matters;
- inspects only relevant existing project context before settling material decisions;
- identifies consequential ambiguity and asks focused questions;
- explores alternatives and tradeoffs when they materially affect behavior, compatibility, risk, or maintenance;
- distinguishes requirements, decisions, non-goals, and deferred questions; and
- creates or updates one matching planned feature Bead.

The planned Bead is a structured, sufficiently lossless record of the conversation. Its description preserves the
outcome and rationale, requirements, relevant repository context, decisions and their reasons, alternatives considered,
non-goals, observable success, failure and compatibility expectations, documentation expectations, and unresolved or
deferred questions. Acceptance criteria summarize externally observable proof without replacing that durable intent.

Planning changes only Beads. It does not pour a workflow molecule, create a branch or worktree, write `design.md`,
create implementation tasks, or commit to Git. Repeated planning resolves and updates the same open planned identity
rather than creating duplicates. Ambiguous identity requires a user decision. Once review has materialized a current
molecule, planning stops: repository-aware refinement belongs to review, and approved scope cannot be changed through
planning.

`/plan-features` remains only as an explicitly deprecated prompt alias to `/plan-feature`. It loads the same skill and
has no independent method or behavior.

### Review feature specification

`/review-feature-spec [feature]` accepts either a planned feature Bead or an already initialized current feature
molecule. For planned intent it invokes the existing idempotent `dstackctl feature initialize` operation to pour or
reuse the stable molecule and conventional worktree, preserving the planned description, acceptance criteria, priority,
and external blocking dependencies. It then scaffolds the canonical `docs/src/features/<slug>/design.md` only when
absent.

The agent materializes the planned intent into that design and reviews it holistically against current architecture,
source, tests, durable docs, dependencies, and other relevant work. It resolves holes and collisions, refines behavior
and boundaries, and decides reuse, interfaces, data flow, validation, failure recovery, security, compatibility,
migration, and documentation impact. It creates bounded outcome-oriented implementation tasks with observable acceptance
criteria and real native dependencies.

Only after the complete design and task graph are reviewed does the command ask for explicit human authorization.
Approval stores the existing SHA-256 digest of accepted design contents, resolves the human gate, and closes the
approval milestone. It stores no Git SHA.

### Implement and close

`/implement-feature` continues to claim and complete only native ready implementation children whose approved design is
unchanged. It does not close the implementation workstream, enter closeout, or start delivery.

`/close-feature` continues to reconcile accepted intent with actual behavior, tests, durable documentation, remaining
findings, full/release validation, and the selected delivery mode. Normal delivery creates no post-delivery Git
bookkeeping mutation.

## Non-goals

- No dStack planning database, state file, packet, ledger, scheduler, readiness calculation, dependency mirror, reviewer
  topology, or Git-to-Beads map.
- No controller-owned product discovery, semantic design writing, architecture judgment, task decomposition, or
  authorization decision.
- No planning-time `design.md`, branch, worktree, workflow molecule, implementation task, or Git commit.
- No retained `/start-feature` prompt, alias, skill, compatibility methodology, or lifecycle stage.
- No second planning skill behind `/plan-features`; the deprecated alias is prompt-only delegation.
- No change to explicit compatibility-only adoption or setup repair.
- No change to the stable four-step molecule unless implementation uncovers a concrete Beads incompatibility.

## Existing patterns and reuse

The redesign reuses the normal planned feature epic labels `dstack:feature-idea` and `feature:<slug>`, current exact
feature resolution, and native Beads create/update/dependency operations. Structured Markdown in the Bead description
carries rich intent without new metadata or a schema store. Existing `feature resolve` plus native `bd create` and
`bd update` operations are sufficient for planning persistence; no controller wrapper is needed solely to rename those
native writes.

Specification review reuses `feature initialize`, `feature scaffold-design`, `feature add-task`, `feature claim-spec`,
and `feature approve-spec`. The initializer already reuses one planned source, preserves durable intent and external
blockers, pours the installed formula, creates or reuses the conventional worktree, and supersedes the source through
native Beads relations. No replacement orchestration command or wrapper state is needed.

The stable molecule remains:

```text
specification -> gated approval -> dynamic implementation children -> closeout
```

The current worktree-scoped selector fallback, approved-design content digest, native ready claims, `Beads: <id>`
footers, fan-in, and delivery guards remain authoritative. The change is primarily a redistribution of agent judgment
and public command responsibilities, not a new workflow engine.

## Design

### Planning boundary

Add one `dstack-beads-plan-feature` skill and `/plan-feature` prompt. The skill first resolves relevant existing feature
ideas and repository context, then runs the interactive discovery conversation. It writes the final structured intent
only after consequential questions are answered or explicitly deferred. It uses Beads' native issue data for identity,
content, priority, and real blocking dependencies, and file-based input for multiline intent so user text is never shell
syntax. It updates only an open planned idea; a current molecule is returned to specification review, and closed or
ambiguous identity requires a user decision.

The existing plural prompt becomes a short deprecated alias that loads `dstack-beads-plan-feature`; the plural skill is
removed so behavior cannot drift. Planning may use deterministic stateless controller resolution where useful, but it
does not require a new persistence abstraction. Exact mechanical choreography belongs in existing `dstackctl` help or
native Beads operations, not in a second workflow model.

### Review boundary

The review skill resolves the selector. When it refers to planned intent, it runs
`feature initialize <selector> --base-branch <base>` before claiming the specification. When it refers to a current
molecule, initialization safely reuses it. In the returned registered worktree, review scaffolds the design only if
missing, translates the full planned Bead into the canonical design, and reconciles it with repository evidence.

Task creation happens during review rather than planning. Each task is a child of the implementation epic, depends on
the approval milestone plus any actual predecessors, and describes an observable outcome rather than a file list or
implementation mechanism. The final graph is reviewed with the design before human authorization.

The existing `feature initialize` command remains public mechanical CLI because review needs it and controller help is
the mechanical contract. It is no longer a public Pi lifecycle stage. `feature scaffold-design` and `feature add-task`
likewise remain deterministic operations invoked from review.

### Surface removal

Delete `prompts/start-feature.md` and `skills/dstack-beads-start-feature/`. Remove start-stage references from README,
lifecycle docs, later feature skills, package-contract tests, and command-text policy where the old slash command is
enumerated. Keep `start-feature` in the stale user-level skill cleanup list so setup archives obsolete copies that could
otherwise shadow the removed package methodology. Already initialized molecules need no migration: review,
implementation, and closeout derive their state from Beads and the registered worktree.

Update formula descriptions only where they describe which public command owns materialization or authorization. Do not
change stable step labels or formula shape solely to rename user-facing decisions.

## Failure / security / compatibility behavior

- Planning rejects or asks about ambiguous IDs, slugs, or normalized titles instead of updating an arbitrary Bead.
- Repeated planning updates one open planned feature and preserves real external blockers. It does not duplicate feature
  identity or create a workflow root; materialized, closed, or approved features are not rewritten through planning.
- A planning failure leaves Git untouched. Incomplete conversation is either resumed from the existing durable Bead or
  explicitly recorded as a deferred question, not hidden in session state.
- Planned descriptions are treated as data, not executable input. User text is passed through argument arrays or files,
  never shell interpolation in the implemented controller path.
- Review initialization is idempotent. Closed, ambiguous, active-legacy, unsafe path, invalid worktree, failed pour, and
  partial task-creation boundaries fail visibly through existing controller guards.
- Design scaffolding never overwrites authored content and retains traversal and symlink-escape protection.
- Already initialized current molecules remain compatible without `/start-feature`. Active legacy workflows still
  require explicit `/adopt-feature`; normal review never performs compatibility repair.
- The deprecated `/plan-features` alias can only delegate to the singular skill and emits no separate state or
  semantics.
- No secrets, transcripts, session identifiers, branches, worktree paths, or Git SHAs are added to planned intent.

## Validation strategy

Behavior-first fast tests should prove:

- the public prompt/skill surface contains `/plan-feature`, the thin deprecated `/plan-features` alias, and no
  `/start-feature` prompt or skill;
- planning guidance requires focused discovery and the complete durable intent fields while forbidding molecule,
  worktree, task, design-file, and Git mutation;
- repeated planned-feature resolution updates one identity, preserves blockers, and fails on ambiguity;
- review guidance initializes planned intent as needed, scaffolds and reconciles canonical design content, builds
  outcome tasks with native dependencies, and asks for authorization only after holistic review;
- initialized molecules remain directly reviewable and later skills contain no dependency on the removed start
  methodology;
- package cleanup, command-policy, formula, docs, and help contracts expose only the intended lifecycle; and
- implementation and closeout retain their existing stop boundaries.

The existing real-Beads smoke scenario should begin with planned intent and exercise review initialization, intent
preservation, worktree/design materialization, dependent task creation, and approval. It should also prove that planning
itself does not create a molecule or repository change and that an already initialized molecule can enter review
directly. Keep the documented two-scenario acceptance boundary rather than adding a third lifecycle model.

Final validation follows the repository release checks: metadata parsing, Python compilation, fast tests, each required
real-Beads acceptance scenario, `git diff --check`, `git fsck`, bundle verification, and clean-clone checks.

## Documentation impact

- **End user/operator:** update README and lifecycle guidance to explain the four decision-oriented stages, the
  Beads-only planning boundary, repository-aware review, deprecated plural alias, and removal of `/start-feature`.
- **Developer/reviewer:** update architecture and development guidance where needed to document planned-intent
  authority, review-time materialization, retained stateless controller operations, task/dependency construction, and
  compatibility for initialized molecules.
- **Future agent/auditor:** this accepted design, the structured planned Bead, current-product docs, formula/controller
  contracts, and behavior-first tests establish intent. No handoff packet, transient status document, or separate agent
  documentation is required.
