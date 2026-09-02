# 0003: Committed-content approval

- **Status:** Superseded
- **Supersedes:** None
- **Superseded by:** [0006](0006-beads-native-control-plane.md)

## Context

A digest of dirty working-tree bytes can authorize content that is not part of the reviewable candidate, while a commit
identifier is unstable under safe Git history rewriting.

## Decision

Feature approval hashes the tracked design blob at candidate `HEAD`. Approval requires the conventional clean worktree
and exact native specification, human gate, and approval milestone convergence. Before any native authorization state
closes, dStack stores and verifies the digest as pending content identity. After native convergence it promotes that
same digest to approved and clears pending. Implementation authorization requires the approved digest and no pending
digest.

## Consequences

Equivalent committed content survives history rewriting. Dirty, untracked, uncommitted, moved, or symlinked designs
cannot be approved. An interrupted approval can resume only against the same pending content; closed native state
without pending or approved identity fails closed. Reauthorization invalidates approved and pending identity before
reopening native authorization boundaries.
