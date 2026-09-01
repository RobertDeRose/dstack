# 0002: One-way Git evidence

- **Status:** Accepted
- **Supersedes:** None
- **Superseded by:** None

## Context

Persisting commit identities in Beads as task, implementation, delivery, evidence, or bookkeeping mappings couples
workflow records to rewriteable Git object names and creates reconciliation work after rebases or amends. A project
audit must compare current code, docs, Beads intent, and Git history; it must not promote a historical repository
snapshot into a second authority.

## Decision

Commits reference work through a `Beads: <id>` footer. dStack discovers current reachable evidence from Git when needed.
Beads never stores task-to-commit, implementation, delivery/finalization, worktree/branch, or reconstructible
audit-result mappings or a mirror of Git history.

No Git revision is stored in Beads. Project-audit findings are read-only agent analysis; accepted corrections become
ordinary feature intent, and execution and delivery revalidate current repository evidence.

## Consequences

Amend, rebase, and cherry-pick require no Beads remapping. Completion and delivery query the relevant reachable source
and reject missing, unexpected, orphaned, or malformed evidence. Multiple distinct reachable commits for one Bead are
valid fixup history and remain visible informationally; repeating the same footer in one commit is malformed. The final
closeout or landing footer must remain reachable through any pre-delivery fixups. A no-repository-change close is
explicit, reasoned, clean, and has no candidate revision.
