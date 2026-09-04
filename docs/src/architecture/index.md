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
             +-- hk and tests
             `-- mdBook validation
```

### Beads

Beads owns feature molecules, plans, decisions, tasks, dependencies, gates, claims, readiness, completion, and native
workflow history.

### Skills

Skills inspect repository evidence, ask material questions, review intent, implement accepted work, and assess audit
findings. They perform semantic judgment through native Beads operations.

### dStack CLI

dStack commands read current Beads, Git, and filesystem facts on each invocation. They validate structure, branch and
worktree identity, Git evidence, documentation, and project checks. They perform no workflow-state calculation.

## Persistent information

| Information | Authority |
| --- | --- |
| Workflow state and relationships | Beads |
| Source, tests, documentation, and history | Git |
| Current product guidance | `docs/` |
| Formatting, linting, and validation | hk |
| Feature formula | Versioned project configuration |

The CLI stores no workflow database, readiness cache, audit snapshot, or commit mapping.
