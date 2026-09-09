# Architecture

dStack separates workflow reasoning from deterministic repository mechanics. The four main responsibilities are kept
small so each source of truth has one clear owner.

## Responsibilities

### Beads

Beads stores the feature workflow: plans, decisions, tasks, dependencies, gates, claims, readiness, completion, and
workflow history.

### Git

Git stores the repository: source, tests, documentation, branches, worktrees, commits, and history.

### Skills

Skills handle semantic work. They clarify intent, review plans against the repository, implement approved tasks, assess
close findings, and decide when a question needs user input. They use the target repository's own validation commands
for project-specific checks.

### dStack CLI

The `dstack` CLI handles deterministic operations such as policy validation, worktree discovery, canonical task commits,
feature checks, and feature-documentation validation. It reads current Beads, Git, and filesystem state for each
invocation.

## Data flow

```text
User request
    |
    v
Workflow command -------- selects a stage-specific skill
    |
    v
Skill ------------------- semantic decisions and user questions
    |
    +-- Beads CLI -------- workflow state and relationships
    |
    `-- dStack CLI ------- deterministic checks and repository operations
             |
             +-- Git and worktrees
             +-- bounded Beads/Git evidence
             `-- feature-document structure
```

A workflow command such as `/review-plan` or `/implement` chooses the skill for that stage. The skill decides what the
work means and what information it needs; Beads and the dStack CLI provide the durable state and deterministic
operations used to carry it out.

## Persistent information

| Information | Stored in |
| --- | --- |
| Feature workflow state and relationships | Beads |
| Source, tests, documentation, and repository history | Git |
| Feature workflow policy | `.beads/formulas/dstack-feature.formula.toml` and `.beads/PRIME.md` |
| Accepted feature intent and implementation tasks | Beads feature issues |
| Published feature documentation | `docs/src/features/<slug>/` in Git |
| Project-specific validation behavior | Target repository tooling and documentation |

Current repository documentation and accepted decisions are the source for current product guidance. Beads memory can
provide useful context, but it is not live workflow state.
