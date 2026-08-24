# 0003: Committed-content approval

- **Status:** Accepted
- **Supersedes:** None
- **Superseded by:** None

## Context

A digest of dirty working-tree bytes can authorize content that is not part of the reviewable candidate, while a commit
identifier is unstable under safe Git history rewriting.

## Decision

Feature approval hashes the tracked design blob at candidate `HEAD`. Approval
requires the conventional clean worktree and exact native specification, human
gate, and approval milestone convergence. The content digest is stored only
after native authorization succeeds.

## Consequences

Equivalent committed content survives history rewriting. Dirty, untracked,
uncommitted, moved, or symlinked designs cannot be approved. Reauthorization
invalidates the digest before reopening native authorization boundaries.
