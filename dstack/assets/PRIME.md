# dStack workflow contract

This project uses dStack only inside an explicitly activated dStack workflow: `/plan-feature`, `/review-plan`,
`/implement`, `/close-feature`, `/audit-project`, or an explicit request to use dStack. Do not infer activation from
`.beads`, installed skills, this file, or `bd` availability. Outside an active workflow, do not run Beads or create
workflow state.

## Authority

Beads owns plans, decisions, tasks, dependencies, gates, claims, readiness, completion, and durable workflow memory. Git
owns repository content, branches, worktrees, and history. Current repository documentation and accepted decisions
outrank stale memory. Never create a parallel task list, readiness cache, commit map, audit packet, recovery journal, or
other shadow workflow state.

dStack owns deterministic mechanics and validation. Skills and the agent own semantic work: planning, review,
implementation, validation choices, and questions that require user authority.

## Using dStack

When the active skill names a dStack operation, use that operation instead of reproducing its mechanics with direct
`git`, `bd`, or filesystem commands. Use only the arguments shown by the skill or `dstack <command> --help`; do not
invent flags or alternate command sequences.

```text
dstack <command> [arguments]
```

A nonzero exit means the operation failed. Read the diagnostic and preserve the Git or Beads state it reports. Do not bypass a
failed invariant manually and then continue as though dStack succeeded.

## Resume and recovery

Resume this agent's existing in-progress Beads work before claiming or creating replacement work. Never take another
owner's claim; report the candidates when ownership is ambiguous. If `dstack worktree` reports `recovery_required`,
enter the returned worktree, inspect `git status`, and finish or deliberately abort the reported native Git operation
before another mutating dStack command. dStack may make retries idempotent, but recovery state remains in Git and Beads
rather than a dStack-owned journal.

Only one agent writes a feature worktree at a time. Preserve existing edits and staged content until ownership is clear.
Beads status is authoritative for completion; an empty ready queue does not by itself prove a task or workflow is
complete.

## Memory

Use memory only when the active skill explicitly permits it. Memory is advisory context, never live status or completion
evidence. Any memory write or correction requires explicit user approval.
