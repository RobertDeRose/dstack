# Beads-native control plane

- **Status:** Accepted

## Decision

The dStack workflow is opt-in. Only an explicit dStack command or request to use dStack activates Beads tracking; the
presence of a Beads workspace, installed skills, or a project formula does not. Ordinary requests do not invoke `bd` or
create Beads issues.

Once activated, Beads owns workflow state and native transitions. Git owns repository content, worktrees, branches, and
history. Skills make semantic decisions and ask the user about material uncertainty. `dstack ctl` performs deterministic
repository mechanics and validation from current Beads, Git, filesystem, and project-check facts.

The feature formula is:

```text
plan -> review -> human approval -> implementation tasks -> audit
```

The controller stores no workflow database, readiness cache, task manifest, audit snapshot, or commit mapping. Native
Beads relationships determine readiness and completion. Git footers provide one-way task evidence when a task commit is
required.

## Consequences

Workflow recovery uses Beads and Git directly only for an explicitly activated dStack workflow. dStack setup must not
install generic Beads agent instructions or automatic `bd prime` hooks; projects initialize Beads with `--skip-agents`.
Current product behavior is documented in the mdBook under `docs/`. Deterministic checks remain small, stateless, and
independently testable. Semantic review and authorization remain with skills and the user.
