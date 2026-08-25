# 0002: One-way Git evidence

- **Status:** Accepted
- **Supersedes:** None
- **Superseded by:** None

## Context

Persisting commit identities in Beads as task, implementation, delivery, evidence, or bookkeeping mappings couples
workflow records to rewriteable Git object names and creates reconciliation work after rebases or amends. An immutable
revision that is itself explicit workflow input is not such a mapping.

## Decision

Commits reference work through a `Beads: <id>` footer. dStack discovers current reachable evidence from Git when needed.
Beads never stores task-to-commit, implementation, delivery/finalization, worktree/branch, or reconstructible
audit-result mappings or a mirror of Git history.

A Git revision may be stored only when its identity is explicit workflow input whose semantics require an immutable
repository snapshot. The sole current exception is `baseline_commit` in the canonical project-alignment plan.

## Consequences

Amend, rebase, and cherry-pick require no Beads remapping. Completion and delivery query the relevant reachable source
and reject missing, unexpected, orphaned, malformed, or outside-candidate evidence. Multiple distinct reachable commits
for one Bead are valid fixup history and remain visible informationally; repeating the same footer in one commit is
malformed. Moving the configured alignment target invalidates authorization until the baseline is reviewed again; it
never triggers commit remapping. A no-repository-change close is explicit, reasoned, clean, and has no reachable footer
evidence.
