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

Select features by canonical `<num>-<slug>`, `F<num>`, or human name through the dstack lifecycle skills. Use the Beads
ID returned by the skill for mutations, but do not expose an opaque hash as the primary workflow command. Inspect
selected work with `bd show <id> --json` and read structured metadata before prose.

### Sources of truth

- **Beads** owns executable work state, dependencies, priorities, claims, findings, and evidence.
- **`docs/src/features/<num>-<slug>/design.md`** owns intended feature behavior, boundaries, decisions, validation, and
  documentation impact.
- **Reader-facing pages under `docs/src/`** own current supported behavior.
- **`docs/src/features/<num>-<slug>/index.md`** owns delivered-feature reconciliation and audit history.
- **`docs/src/planned-features.md`** is the human roadmap; Beads remains authoritative for live state.
- **Code and tests** provide implementation evidence.

Use Beads instead of Markdown TODO lists for executable work. Use `bd remember` for durable cross-feature knowledge.

### Feature identity

Allocate immutable, zero-padded feature numbers in increments of ten:

```text
docs/src/features/010-first-capability/
feat/010-first-capability
```

Each feature is one Beads epic (a poured molecule uses epic hierarchy with workflow semantics). Store `feature_number`,
`feature_slug`, `feature_name`, `design_path`, `implemented_path`, and `base_branch` on that root. Put lifecycle tasks
and bounded implementation tasks beneath the epic. The implementation coordinator remains a task gate, not a second
feature or milestone. Never renumber a feature because priority or dependency order changes.

Start features with a human reference, for example:

```text
/start-feature 010-first-capability
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
/close-feature
/audit-project
```

The Skills CLI manages installed skill files. This repository owns the canonical Copier source; generated projects
record and update their scaffold through `.copier-answers.yml`.

### Beads lifecycle

The project-local formula is `.beads/formulas/feature-lifecycle.formula.toml`. It defines interactive design, isolated
specification reviews, specification reconciliation, implementation, documentation reconciliation, validation, holistic
close-out reviews, and explicit delivery.

Use dependency types intentionally:

- `blocks`: a real prerequisite that affects readiness;
- `parent-child`: hierarchy only;
- `related`: contextual association;
- `discovered-from`: provenance for work found during execution.

For each implementation task: claim it atomically, load only relevant design and documentation context, implement the
smallest complete scope, update documentation in the same work unit, validate, run an isolated
quality/security/maintainability review, record evidence, commit with the Beads ID, and close only after acceptance
criteria pass. Use focused checks while iterating. Run the full repository suite once after review fixes stabilize and
before commit; rerun it only after a failure or a later broad/shared fix.

### Review orchestration

Initial reviewers always use fresh context. A workflow with two or more review roles first launches exactly one fresh,
read-only context builder. It writes an ephemeral factual packet covering authority, requirements, architecture, changed
files, Beads state, documentation impact, validation evidence, and exact source locations. The packet contains no
findings, recommendations, or verdict and is never committed.

Pass that same packet to each fresh role reviewer. Reviewers reason independently, verify role-critical evidence, and
read extra source only when the packet is insufficient. `/implement-feature` uses one fresh reviewer per task without a
context builder; `/start-feature` uses one context builder plus four reviewers; `/close-feature` uses one context
builder plus two reviewers. Do not add confidence reviewers without a distinct uncovered risk or an explicit user
request.

After a fix, resume only the original reviewers whose domains changed. Do not launch fresh follow-up reviewers unless
the original cannot be resumed or the fix materially changes the review scope. Give a replacement the original packet
when one exists, plus findings, resolutions, and the post-review diff. Refresh the shared packet only after broad
design, architecture, task-graph, or documentation-structure changes.

### Commit messages

For multiline messages, write the message to a temporary file and use `git commit -F <file>`; one argument containing
literal newlines is also valid. A single `-m` is acceptable only for a subject-only commit. Never construct bodies with
multiple `-m` flags or escaped `\n` text. Verify the resulting message before recording its SHA in Beads.

### Worktrees and delivery

Feature branches use `feat/<num>-<slug>`. When `wt` is available, treat JSON output from `wt switch --format json` as
authoritative for branch and path.

Only fast-forward merges into `main` are accepted. Use `git merge --ff-only`; never create a merge commit and never fall
back to one when fast-forwarding fails.

A no-mode `/close-feature` completes close-out and then asks for one explicit action:

```text
create PR
merge
leave ready with no delivery action
```

<!-- END DSTACK WORKFLOW -->
