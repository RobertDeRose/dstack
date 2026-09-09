# Architecture

## Authority boundaries

dStack is an opt-in workflow around two existing authorities:

- **Beads** owns workflow state: features, plans, decisions, tasks, dependencies, gates, claims, readiness, completion,
  and workflow history.
- **Git** owns repository state: source, tests, documentation, branches, worktrees, commits, and history.

The target repository owns its own validation commands. dStack does not add another task database, readiness engine,
branch registry, recovery journal, or project-validation framework.

```text
User request
    |
    v
Workflow command -------- chooses the stage-specific skill
    |
    v
Skill ------------------- semantic decisions and user questions
    |
    +-- Beads CLI -------- workflow graph and state
    |
    `-- dStack CLI ------- deterministic checks and repository mechanics
             |
             +-- Git and worktrees
             +-- bounded Beads/Git evidence
             `-- feature-document structure
```

## Workflow commands and skills

The installed workflow commands are `/plan-feature`, `/review-plan`, `/implement`, `/close-feature`, and
`/audit-project`. Invoking one loads its corresponding skill. Skills perform semantic work: asking material questions,
reconciling intent with repository evidence, implementing approved work, reviewing close findings, and assessing project
drift.

The workflow does not activate merely because Beads, dStack resources, or `.beads/PRIME.md` are present.

## dStack CLI

The CLI reads current Beads, Git, and filesystem facts on every invocation. It performs deterministic operations such as
policy checks, branch/worktree validation, canonical commit handling, feature checks, and feature-documentation
validation.

The CLI does not calculate workflow readiness or choose what should happen next. Skills use Beads for those transitions.
When detailed evidence is needed, they use the existing Beads and Git interfaces rather than a second dStack detail API.

## Persistent information

| Information | Authority |
| --- | --- |
| Workflow state and relationships | Beads |
| Source, tests, documentation, and Git history | Git |
| Current product guidance | Repository documentation |
| Project validation | Target repository tooling |
| Feature workflow policy | Versioned dStack formula and `.beads/PRIME.md` |

Current repository documentation and accepted decisions outrank stale memory. Memory is advisory context, never live
workflow state.
