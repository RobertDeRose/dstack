# Architecture

## Authority boundaries

```text
User request
    |
    v
Targeted skill ---- semantic judgment and user questions
    |
    +---- native Beads commands ---- workflow graph and next work
    |
    `---- dstack ctl ------------ deterministic repository mechanics
                 |
                 +---- Git/worktrees
                 +---- hk/tests
                 `---- mdBook/docs validation
```

### Beads

Beads owns initialization, workspace health, feature molecules, plans, questions, answers, decisions, task
decomposition, dependencies, gates, claims, readiness, completion, synchronization, external trackers, and agent-facing
workflow context. Native `blocks` and `waits-for` edges determine availability. dStack never calculates positive
readiness.

### Skills

Skills own reasoning that cannot be made deterministic: finding ambiguities, reviewing plans, interpreting
implementation behavior, assessing documentation, and deciding whether drift is clear or requires user authority. They
guide native Beads operations rather than defining another lifecycle.

### dStack CLI

The CLI is stateless with respect to workflow. It reads current Beads and Git facts on every invocation and may enforce:

- installation and verification of the packaged dStack formula;
- feature branch and conventional worktree policy;
- plan/task structure inside native Beads fields;
- native task-graph membership required by the dStack formula;
- Conventional Commit formatting and one-way Beads evidence;
- mandatory hk validation and worktree cleanliness;
- mdBook navigation, links, and build validity; and
- bounded audit evidence collection with explicit detail expansion.

The repository mutation lock serializes local dStack Git/worktree operations. It is synchronization, not durable
workflow state.

## Persistent information

| Information | Authority |
| --- | --- |
| Work status, dependencies, questions, decisions | Beads |
| Current product/architecture/operations behavior | Repository documentation |
| Code and change history | Git |
| Project formatting/testing policy | hk and repository configuration |
| dStack formula | Versioned project configuration |

No dStack database, readiness cache, phase file, approval journal, formula-swap journal, worktree registry, validation
cache, audit result, or task-to-commit map exists.
