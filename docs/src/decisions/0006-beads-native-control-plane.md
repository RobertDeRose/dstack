# 0006: Beads-native control plane

- **Status:** Accepted
- **Supersedes:** [0003](0003-committed-content-approval.md), [0004](0004-root-open-until-delivery.md), [0005](0005-interactions-and-documentation.md)
- **Superseded by:** None

## Context

The controller accumulated lifecycle projection, planned-root replacement,
approval transaction state, dynamic fan-in checks, formula-swap recovery, and an
implicit delivery phase. Those mechanisms duplicated Beads and increased the
context agents needed to resume work.

## Decision

One persistent Beads molecule owns planning, independent review, human approval,
implementation tasks, and final audit. Native dependencies, gates, claims, and
ready-work output are authoritative.

dStack is limited to deterministic formula installation, branch/worktree policy,
plan/task validation, commit formatting, reachable evidence checks, documentation
validation, and read-only audit evidence. Skills ask questions and make semantic
judgments. Approval is represented by the native human gate and approval-task
history; no second digest state machine is maintained. Delivery is ordinary
project work when required, never an implicit state inferred by dStack.

## Consequences

Agents resume from Beads rather than Markdown. Implementation tasks include the
current documentation they affect. Drift becomes ordinary remediation work or a
native human gate when authority is ambiguous. Historical molecules are not
migrated to newer formula topology. The controller can remain small and stateless
with respect to workflow.
