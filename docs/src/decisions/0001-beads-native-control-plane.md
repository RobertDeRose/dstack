# Beads-native control plane

- **Status:** Accepted

## Decision

The dStack workflow is opt-in. Only `/plan-feature`, `/review-plan`, `/implement`, `/close-feature`, `/audit-project`,
or an explicit request to use dStack activates Beads tracking; the presence of a Beads workspace, installed skills, or a
project formula does not. dStack setup, checks, and deterministic repository commands do not create workflow issues.
Ordinary requests do not invoke `bd`.

Once activated, Beads owns workflow state and native transitions. Git owns repository content, worktrees, branches, and
history. Skills make semantic decisions and ask the user about material uncertainty. dStack performs deterministic
repository mechanics and validation from current Beads, Git, filesystem, and project-check facts.

The feature formula is:

```text
plan -> review -> human approval -> implementation tasks -> close
```

The controller stores no workflow database, readiness cache, task manifest, audit snapshot, or commit mapping. Native
Beads relationships and gates determine readiness and completion. The close skill performs semantic review before
claiming the final step; native implementation fan-in blocks that step whenever implementation work is open. Human gates
are created only for actual approval or material ambiguity. Git trailers provide one-way task evidence when a task
commit is required.

The installed `PRIME.md` defines only the universal interaction contract: activation, native authority, generic dStack
invocation, failure handling, and resume/recovery. Each workflow skill documents only the dStack operations needed by
that stage, when to invoke them, and concise examples. Exact flags and deterministic mechanics belong to the CLI help
and command-reference documentation rather than being repeated across skills.

## Consequences

Workflow recovery uses Beads and Git directly only for an explicitly activated dStack workflow. dStack setup must not
install generic Beads agent instructions or automatic `bd prime` hooks; projects initialize Beads with `--skip-agents`.
Current product behavior is documented in the mdBook under `docs/`. Deterministic checks remain small, stateless, and
independently testable. Recovery paths are required behavior even when they are not exercised during normal execution:
dStack detects native interrupted Git/Beads state, preserves it, and makes safe retries idempotent where possible rather
than creating a shadow recovery store. Semantic review and authorization remain with skills and the user.
