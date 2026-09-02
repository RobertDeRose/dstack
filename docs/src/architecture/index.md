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

Beads owns feature molecules, plans, questions, answers, decisions, task
decomposition, dependencies, gates, claims, readiness, and completion. Native
`blocks` edges determine availability. dStack never calculates positive
readiness.

### Skills

Skills own reasoning that cannot be made deterministic: finding ambiguities,
reviewing plans, interpreting implementation behavior, assessing documentation,
and deciding whether drift is clear or requires user authority.

### dStack CLI

The CLI is stateless with respect to workflow. It reads current Beads and Git
facts on every invocation and may enforce:

- formula installation and contract validation;
- feature branch and conventional worktree policy;
- plan/task document structure inside native Beads fields;
- Conventional Commit formatting and one-way Beads evidence;
- worktree cleanliness and reachable commit evidence;
- mdBook navigation, links, and build validity; and
- compact audit evidence collection.

The repository mutation lock serializes local dStack Git/worktree operations. It
is synchronization, not durable workflow state.

## Persistent information

| Information | Authority |
| --- | --- |
| Work status, dependencies, questions, decisions | Beads |
| Current product/architecture/operations behavior | Repository documentation |
| Code and change history | Git |
| Project formatting/testing policy | hk and repository configuration |
| Formula and dStack policy | Versioned project configuration |

No dStack database, readiness cache, phase file, approval journal, formula-swap
journal, worktree registry, or task-to-commit map exists.
