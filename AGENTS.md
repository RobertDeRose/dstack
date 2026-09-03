# dStack agent contract

## Authority

Beads is the sole authority for workflow state, questions, decisions, tasks,
dependencies, gates, claims, readiness, and completion. Git is the authority for
repository content and history. Current repository documentation is the
published description of current behavior.

dStack is not a workflow engine. Do not add a task database, lifecycle enum,
phase detector, ready-work calculation, branch registry, worktree registry,
commit-SHA map, handoff packet, migration ledger, or custom coordination
protocol.

## Workflow

Use the native `dstack-feature` molecule:

```text
plan -> review -> human approval -> implementation children -> audit
```

Start and resume work from native Beads queries. A skill may filter the ready
queue by parent and label, but it must not recalculate readiness or override a
native blocker.

Planning must perform an explicit ambiguity pass and ask the user material
product, architecture, compatibility, operational, or security questions before
closing the plan. Questions, answers, decisions, rationale, and acceptance
criteria belong in Beads.

Review compares the plan against current code, tests, documentation, and prior
decisions. It creates bounded native implementation tasks atomically with their
approval blockers; task-to-task blockers are used only for real execution order.
Invocation is not approval; the formula-generated human gate is resolved only
after explicit user approval.

Implementation claims one native ready task. Code, tests, configuration, and the
current documentation describing the changed behavior belong to the same task.
The audit step detects implementation, documentation, plan, and decision drift.
Ambiguous authority requires a human gate and a targeted user question.

## Deterministic mechanics

`dstack ctl` may:

- install and verify the project formula;
- enforce branch and worktree naming/path policy using native Beads worktrees;
- validate plan and task structure;
- generate Conventional Commit messages and one `Beads: <id>` footer;
- inspect reachable Git evidence;
- validate current documentation; and
- collect read-only audit evidence.

It must not claim, close, reopen, approve, or select Beads work on behalf of the
agent. Those are explicit native Beads operations in the targeted skills.

## Documentation

Every implementation task must classify impact on:

- end users: behavior, configuration, deployment, operations, migration, and
  troubleshooting;
- developers: architecture, interfaces, data flow, extension points, and tests;
- future agents: current invariants plus searchable decision rationale.

Repository documentation describes current truth. Decision Beads preserve why.
Do not require feature-history Markdown, duplicate task lists, transcripts, live
workflow status, commit identities, worktree paths, or next-command bookkeeping
in documentation.

## Git and validation

Use `dstack ctl git commit` or `dstack ctl git amend`; do not hand-write the
subject. A commit references its task with exactly one `Beads: <id>` footer.
Never store Git SHAs in Beads.

Run focused tests while working and `hk check -a` before closing an implementation
task. Beads lifecycle hooks are chained through hk. Keep generated or runtime
Beads database content out of implementation commits.

## Engineering constraints

- Python baseline: 3.14 with complete type hints.
- Keep functions focused and interfaces narrow.
- Prefer native Beads and Git operations over adapters.
- Preserve deterministic JSON output for agent-facing commands.
- Add real-Beads acceptance coverage for every relied-upon native behavior.
