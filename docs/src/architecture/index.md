# Architecture

## Authority boundaries

The dStack workflow is opt-in. The presence of Beads, installed skills, or a project formula does not activate task
tracking. Only an explicit workflow command or request to use dStack crosses the workflow boundary; an explicitly
requested `dstack ctl` command may perform its documented mechanics but does not create workflow issues. Ordinary
requests do not invoke Beads.

```text
User request
    |
    v
Targeted skill -- semantic decisions and user questions
    |
    +-- native Beads commands -- workflow graph and state
    |
    `-- dstack ctl ----------- deterministic repository mechanics
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

`dstack ctl` reads current Beads, Git, and filesystem facts on each invocation. It validates structure, branch and
worktree identity, Git evidence, documentation, and project checks. It performs no workflow-state calculation.

## Persistent information

| Information | Authority |
| --- | --- |
| Workflow state and relationships | Beads |
| Source, tests, documentation, and history | Git |
| Current product guidance | `docs/` |
| Formatting, linting, and validation | hk |
| Feature formula | Versioned project configuration |

The CLI stores no workflow database, readiness cache, audit snapshot, or commit mapping.
