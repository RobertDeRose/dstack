### Goals

Use Beads as the durable source of feature workflow state and Git as the durable source of repository state. Keep dStack
focused on deterministic validation and repository mechanics instead of maintaining a second workflow model. Preserve
safe restart and recovery from the state already recorded by Beads and Git, while leaving semantic decisions and user
authorization to skills and the user.

### User-facing behavior

The dStack workflow is activated only by `/plan-feature`, `/review-plan`, `/implement`, `/close-feature`,
`/audit-project`, or an explicit request to use dStack. Repository setup, policy checks, installed skills, and the
presence of a Beads workspace do not create feature work by themselves.

The feature lifecycle is:

```text
plan -> review -> human approval -> implementation tasks -> close
```

Feature and task progress, claims, dependencies, gates, and completion remain visible in Beads. Repository changes,
worktrees, commits, and interrupted Git operations remain visible in Git. A later session resumes those existing records
rather than creating replacement workflow or recovery state.

### Implemented design

Beads owns plans, decisions, tasks, dependencies, gates, claims, readiness, completion, and workflow history. Git owns
repository content, branches, worktrees, commits, and history. Skills own semantic reasoning and questions that require
user input. The dStack CLI reads current Beads, Git, filesystem, and project-validation facts for deterministic checks
and repository operations.

dStack stores no workflow database, readiness cache, task manifest, feature-check snapshot, commit map, or recovery
journal. Beads relationships and gates determine readiness and completion. Each implementation task is a persistent
ordinary blocker of the close step, so reopening a completed task blocks close again without rebuilding workflow state.
Human gates are used for actual approval or material ambiguity. Git `Task:` trailers provide one-way ownership evidence
for repository-changing implementation tasks.

The installed `.beads/PRIME.md` contains the workflow-wide interaction contract shared by every skill. Individual skills
contain only the semantic steps and dStack operations needed by their workflow stage. Exact CLI arguments and
deterministic mechanics remain in CLI help and reference documentation.

### Compatibility and constraints

Repository initialization must not install generic Beads agent instructions or automatic `bd prime` hooks. dStack
initializes Beads with agent setup disabled and installs only its own repository policy.

Recovery depends on the underlying Beads and Git state remaining available. dStack detects interrupted Git and Beads
state and preserves it for explicit recovery rather than replacing it with dStack-owned state.

The workflow policy and compatibility-sensitive Beads identities remain repository-visible project policy and are
validated separately from semantic workflow decisions.

### Validation

Real-Beads acceptance tests exercise initialization, feature readiness, claims, persistent close blockers, worktree
recovery, task reopening, canonical commits, and interrupted Git operations. Fast tests validate deterministic policy,
Git evidence, command behavior, and documentation contracts without requiring a Beads process.

The repository's normal test, lint, formatting, and release checks validate the implementation around those acceptance
boundaries.

### Non-goals

- Maintaining a separate dStack workflow database, readiness engine, task registry, or recovery journal.
- Caching Beads task state or mirroring Git history in dStack metadata.
- Replacing Git worktree, commit, or interrupted-operation state with dStack-owned state.
- Installing generic Beads agent behavior or automatically activating feature tracking during repository setup.
- Moving semantic planning, review, approval, or ambiguity resolution into deterministic CLI commands.
