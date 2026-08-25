# Security and trust boundaries

dStack coordinates trusted local tools; it is not a sandbox. Repository files, Beads issue content, formula source,
documentation, Git refs, remote responses, and GitHub PR text are instruction and data surfaces that may be attacker
controlled. Review them before authorizing mutation.

## Privileges and confirmation

Controller subprocesses inherit the invoking user's filesystem, Git, Beads, and GitHub privileges. Use least-privilege
credentials and repository-scoped GitHub permissions. Human confirmation is required for specification authorization, PR
content, force setup repair, destructive cleanup, rollback, and history rewrite. A finite review count never replaces
authorization.

Path validation keeps managed documentation and worktrees inside their expected roots and rejects symlink traversal.
Setup resolves every reviewed filesystem, formula, snapshot, and restore path against the repository root before use,
including nonexistent destinations through their nearest existing ancestor. These checks and the later filesystem
operation are separate system calls, not a filesystem sandbox: a process with concurrent write access could replace a
path component between them. Run setup only in a trusted, quiescent checkout and inspect repository and external paths
after any interrupted or suspicious run. Commands use structured argument arrays, not shell interpolation. Timeouts
report whether an operation may have mutated state; callers must inspect the native authority before retrying.

## Sensitive data

Do not place secrets, credentials, private keys, access tokens, customer data, or unredacted incident material in Beads
descriptions, comments, interaction logs, documentation, commit messages, PR text, or command output. Git and Beads
history may be durable and replicated.

`.beads/interactions.jsonl` can contain prompts, decisions, and operational context. It remains local, ignored, and
untracked. Limit access and retention, and redact exports. Repository documentation records durable product intent and
reasoning, not private transcripts or transient workflow details.

## Force and recovery boundaries

`--force` permits only reviewed setup compatibility repair; it is not a general bypass for validation. Direct delivery
remains fast-forward-only. dStack never automatically resets, force-pushes, rewrites history, or deletes uncertain data.
Use native Git, Beads, Dolt, and GitHub recovery procedures with explicit user authorization and verified backups.
