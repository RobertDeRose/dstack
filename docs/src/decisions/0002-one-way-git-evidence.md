# 0002: One-way Git evidence

- **Status:** Accepted
- **Supersedes:** None
- **Superseded by:** None

## Context

Persisting commit identities in Beads couples workflow records to rewriteable
Git object names and creates reconciliation bookkeeping after rebases or amends.

## Decision

Commits reference work through a `Beads: <id>` footer. dStack discovers current
reachable evidence from Git when needed. Beads never stores commit hashes or a
mirror of Git history.

## Consequences

Amend, rebase, and cherry-pick require no Beads remapping. Completion and
delivery must query the relevant reachable range and reject missing or
unexpected evidence. A no-repository-change close is explicit, reasoned, clean,
and has no reachable footer evidence.
