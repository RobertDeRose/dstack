# AGENTS.md — dstack

<!-- BEGIN DSTACK WORKFLOW -->
## dstack workflow

### Session start

Run before selecting work:

```bash
bd prime
bd ready --type epic --label workflow:feature --json --limit 0
bd ready --json
```

Select features by canonical `<slug>` or human name through the dstack lifecycle skills. Use the Beads ID returned by
the skill for mutations, but do not expose an opaque hash as the primary workflow command. Inspect selected work with
`bd show <id> --json` and read structured metadata before prose.

### Sources of truth

- **Beads** owns executable work state, dependencies, priorities, claims, findings, and evidence.
- **`docs/src/features/<slug>/design.md`** owns intended feature behavior, boundaries, decisions, validation, and
  documentation impact.
- **Reader-facing pages under `docs/src/`** own current supported behavior.
- **`docs/src/features/<slug>/index.md`** owns delivered-feature reconciliation and audit history.
- **`docs/src/planned-features.md`** is the human roadmap; Beads remains authoritative for live state.
- **Code and tests** provide implementation evidence.

### Project context

- **Purpose:** Keep product intent, work, documentation, evidence, and delivery aligned.
- **Intended users:** Maintainers, coding agents, and teams delivering software through the dstack workflow.
- **Current supported scope:** Skills, Copier templates, Beads lifecycles, workflow helpers, validation, and delivery
  docs.
- **Boundaries:** Workflow and documentation contracts; no application framework or universal build system.
- **Project kind:** `other`
- **Language profiles:** `python`

Use Beads instead of Markdown TODO lists for executable work. Use `bd remember` for durable cross-feature knowledge.

### Feature identity

Use an immutable lowercase filesystem-safe slug as each feature identity:

```text
docs/src/features/first-capability/
feat/first-capability
```

Each feature is one Beads epic (a poured molecule uses epic hierarchy with workflow semantics). Store `feature_slug`,
`feature_name`, `design_path`, `implemented_path`, and `base_branch` on that root. Put lifecycle tasks and bounded
implementation tasks beneath the epic. The implementation coordinator remains a task gate, not a second feature or
milestone. Roadmap order and dependencies remain explicit rather than encoded in feature identity.

Start features with a human reference, for example:

```text
/start-feature first-capability
/start-feature "First capability"
```

### Documentation placement

Place documentation by reader intent:

- **Introduction**: purpose, audience, scope, boundaries, and conventions.
- **Architecture**: structure, ownership, interactions, invariants, and durable decisions.
- **Operator's Manual / Usage**: use, deployment, configuration, observability, maintenance, recovery, and
  troubleshooting where applicable.
- **Development Guide**: build, testing, extension, migration, and maintenance.
- **Reference**: exact commands, configuration, interfaces, schemas, fields, states, defaults, limits, terminology, and
  acceptance contracts.
- **Implemented Features**: one standalone delivery and audit record per completed feature.

Create project-specific pages only for durable reader needs. Feature designs name exact pages, not only documentation
sections.

### Workflow skills

Install or refresh dstack skills with:

```bash
npx --yes skills@1.5.16 add RobertDeRose/dstack
npx skills update
```

The workflow commands are:

```text
/setup-project
/update-project
/plan-features
/start-feature
/implement-feature
/implement-task
/close-feature
/audit-project
```

The Skills CLI manages installed skill files. This repository owns the canonical Copier source; generated projects
record and update their scaffold through `.copier-answers.yml`.

### Beads lifecycle

The project-local formula is `.beads/formulas/dstack-feature.formula.toml`. It defines interactive design, isolated
specification reviews, specification reconciliation, implementation, documentation reconciliation, validation, direct
specialized close-out reviews, and explicit delivery.

Use dependency types intentionally:

- `blocks`: a real prerequisite that affects readiness;
- `parent-child`: hierarchy only;
- `related`: contextual association;
- `discovered-from`: provenance for work found during execution.

Native linked-worktree Beads authority is shared. `bd -C` is not an interaction-isolation boundary. All dstack Beads
mutation intervals use `skills/dstack-core/references/INTERACTION-BOUNDARY.md` and the repository-scoped lease from
`skills/dstack-core/scripts/beads-workflow-lock.py`. Foreign interaction rows remain blocking and must stay with their
owning work unit; never broaden lineage, discard rows, or restore over a rejected snapshot. Native Dolt publication uses
`skills/dstack-core/scripts/guarded-beads-push.py`; never replace it with raw or force publication. Delivery and
feature-root issues remain open until the guarded post-merge finalizer verifies the merge and documentation evidence.

Use issue types intentionally. Feature roots are `epic`; lifecycle gates and ordinary bounded work are `task`; known
defects are `bug`; timeboxed fact-finding with explicit exit criteria is `spike`; durable architecture or product
choices are `decision`; and maintenance is `chore`. Use `feature` for standalone enhancements outside a feature epic.
Introduce `story` only when the repository actually manages a user-story backlog, and `milestone` only as a work-free
aggregate. Labels and metadata, not extra issue types, own workflow phase and review role.

For each implementation task: claim it atomically, load only relevant design and documentation context, run a semantic
boundedness check before mutating code, record the executing skill version using the installed dstack-core evidence
contract, implement the smallest complete scope, update documentation in the same work unit, validate, run an isolated
quality/security/maintainability review, record evidence, commit with the Beads ID, and close only after acceptance
criteria pass. Use `/implement-task` for one standalone executable issue; `/implement-feature` continues through a
reviewed feature's children, running a cohesion checkpoint after each child; if remaining work gains an independent
value or review boundary, pause and return to normal feature planning rather than adding children under an incoherent
coordinator. Use focused checks while iterating. Run only affected checks declared by the selected task and its exact
acceptance criteria. The implementation lifecycle does not automatically run the entire repository suite; run it only
after an explicit user request or when a separate repository delivery policy requires it.

### Review orchestration

All reviewers use fresh, narrow context and direct Beads-derived assignments. `/start-feature` launches exactly two
independent reviewers concurrently: specification clarity and execution readiness. `/implement-feature` and
`/implement-task` launch one focused task reviewer. `/close-feature` launches concurrent implementation-integrity and
delivery-integrity reviewers. There is no LLM context builder.

The optional Pi adapter maps `specification-clarity`, `execution-readiness`, `task`, `implementation-integrity`, and
`delivery-integrity` to the exact definitions in `skills/dstack-core/references/PI-REVIEWER-ROSTER.md`. It never changes
counts or mutates Pi configuration. Missing or unavailable names fail visibly after the explicit optional sync; there is
no silent role substitution.

Beads is the workflow manifest. The controller derives transient assignments from current Beads/design/docs/validation
and one immutable Git source boundary; execution readiness also receives a validated transient Beads graph projection
that works with embedded Dolt. It never builds a shared packet or second durable manifest. Beads remains review
authority. Append executable `Review state:` and `Finding:` records through the structured note helper, preserve
current-open projections and historical evidence, resume only affected original reviewers, and enforce one initial plus
one verification pass. Infrastructure replacement is separate from redesign. Protected security, correctness,
validation, accessibility, and data-loss findings cannot be waived.

Existing old-topology graphs migrate only through `migrate-review-topology.py` from the canonical primary worktree under
the repository lease. Old evidence is preserved as superseded history, approval never transfers, and stale controllers
fail closed after the cutover marker.

### Execution efficiency

Do bounded work directly in the controlling session. Launch subagents only when a lifecycle explicitly requires them,
the user asks for delegation, or a distinct independent risk materially benefits from parallel read-only work. Do not
launch a scout, planner, or reviewer merely to save parent context, and never add unrequired confidence reviews.

Reuse existing review results and validation evidence while their source boundaries remain unchanged. After a fix,
resume the affected reviewer instead of starting a replacement. Do not rerun a successful check unless relevant inputs
changed; run exact task validation and affected documentation checks without adding an automatic full suite.

Keep verbose output out of the conversation context. Redirect long command output to an ephemeral file, inspect only the
relevant failure excerpt, and report the command, result, and artifact path. Do not poll background work; continue
useful work or use event-driven waiting.

### Commit messages

Every changelog-visible `feat`, `fix`, `perf`, or `refactor` subject must use `<type>(<scope>): <summary>` or
`<type>(<scope>)!: <summary>`, with a scope from `cog.toml`. Omitted internal types may be unscoped; release commits use
`release: vX.Y.Z`. Choose the owning subsystem from the README's Commit scopes table, not a feature number or incidental
file name. When scopes change, update `cog.toml`, the README table, and this guidance together.

When a body records multiple discrete changes, decisions, or validation results, prefer a Markdown `-` list with one
idea per item. Use prose when sequence, causality, or rationale cannot be adequately expressed as a list; do not force a
body when the subject is sufficient.

For multiline messages, write the message to a temporary file and use `git commit -F <file>`; one argument containing
literal newlines is also valid. A single `-m` is acceptable only for a subject-only commit. Never construct bodies with
multiple `-m` flags or escaped `\n` text. Verify the resulting message before recording its SHA in Beads.

### Worktrees and delivery

Feature branches use `feat/<slug>`. When `wt` is available, treat JSON output from `wt switch --format json` as
authoritative for branch and path.

Only fast-forward merges into `main` are accepted. Use `git merge --ff-only`; never create a merge commit and never fall
back to one when fast-forwarding fails.

A no-mode `/close-feature` completes close-out and then asks for one explicit action:

```text
create PR
merge
leave ready with no delivery action
```

After a confirmed merge, `/close-feature` must update the implemented record with the actual merge SHA, reconcile
reader-facing delivery claims, run the semantic delivery verifier and documentation checks, commit that post-merge
finalizer, and only then close delivery/root state. Stale merge-pending claims block completion.

<!-- END DSTACK WORKFLOW -->
