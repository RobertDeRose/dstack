# Security and trust boundaries

dStack coordinates trusted local tools; it is not a sandbox. Repository files,
Beads content, formulas, documentation, Git refs, and hook configuration are
instruction and data surfaces that may be attacker controlled. Review them
before authorizing mutation.

## Privileges and confirmation

Controller subprocesses inherit the invoking user's filesystem, Git, Beads, and
hook privileges. Use least privilege. Explicit user approval is required before
resolving the feature's native human gate. History rewrites, destructive cleanup,
force operations, and repository delivery remain separately authorized native
Git or hosting-provider operations.

Path validation keeps formulas, worktrees, and installed Pi resources inside
their expected roots and rejects symlink traversal. Commands use argument arrays,
not shell interpolation. A concurrent privileged process can still race local
filesystem checks; run mutations only in a trusted checkout and inspect native
Git/Beads state after an interrupted command.

## Sensitive data

Do not put secrets, credentials, private keys, customer data, or unredacted
incident material in Beads descriptions/comments/history, documentation, commit
messages, or command output. Git and Beads data may be durable and replicated.

`.beads/interactions.jsonl`, when native Beads audit is enabled, may contain
prompts and operational context. Keep it local or apply the project's explicit
retention and redaction policy. Current documentation and decision Beads should
record durable technical facts, not private transcripts.

## Recovery boundaries

There is no general force bypass for dStack validation and no dStack recovery
journal. Recover workflow state with native Beads and Dolt tools. Recover
repository state with native Git. dStack reports retained or ambiguous state
instead of guessing which mutation completed.
