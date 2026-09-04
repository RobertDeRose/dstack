# Architecture

## Authority boundaries

The dStack workflow is opt-in. The presence of Beads, installed skills, or a project formula does not activate task
tracking. Only an explicitly invoked workflow skill or request to use dStack crosses the workflow boundary. dStack
commands may perform their documented mechanics but do not create workflow issues. Ordinary requests do not invoke
Beads.

```text
User request
    |
    v
Targeted skill -- semantic decisions and user questions
    |
    +-- native Beads commands -- workflow graph and state
    |
    `-- dstack -------------- deterministic repository mechanics
             |
             +-- Git and worktrees
             +-- bounded Beads/Git evidence
             `-- feature-document structure
```

### Beads

Beads owns feature molecules, plans, decisions, tasks, dependencies, gates, claims, readiness, completion, and native
workflow history.

### Skills

Public prompts explicitly load hidden, non-model-invocable skills. Skills ask material questions, reconcile targeted
memory with repository evidence, implement accepted work, review close findings, and audit project drift. They perform
semantic judgment through native Beads operations. Current documentation and accepted decisions outrank memory; memory
writes require user approval.

### dStack CLI

dStack commands read current Beads, Git, and filesystem facts on each invocation. They batch multi-issue Beads reads,
bound default evidence, omit commit paths unless requested, and validate structure, branch and worktree identity, Git
evidence, and feature documentation. They perform no workflow-state calculation. Skills run the target repository's
documented project-validation contract.

## Persistent information

| Information | Authority |
| --- | --- |
| Workflow state and relationships | Beads |
| Source, tests, documentation, and history | Git |
| Current product guidance | `docs/` |
| Project validation | Target repository tooling |
| Feature formula | Versioned project configuration |

The CLI stores no workflow database, readiness cache, audit snapshot, or commit mapping.
