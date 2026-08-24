# 0005: Local interactions and durable documentation

- **Status:** Accepted
- **Supersedes:** None
- **Superseded by:** None

## Context

Agent interaction logs may contain private prompts and operational detail, while future users and maintainers need
durable reviewed product intent.

## Decision

`.beads/interactions.jsonl` remains local, ignored, and untracked. Canonical mdBook documentation stores stable product,
architecture, operations, security, reference, decision, and feature-record content shared by humans and agents.

## Consequences

Interaction retention and redaction are operator privacy responsibilities. Documentation must not embed transcripts,
secrets, live workflow state, commit identities, worktree paths, or next-command bookkeeping. The controller and
documentation validation enforce the interaction policy and canonical book.
