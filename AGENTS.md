# dStack agent contract

## Authorities

When the dStack workflow is active, Beads owns plans, decisions, tasks, dependencies, gates, claims, readiness, and
completion. Git owns repository content, branches, worktrees, and history. Repository documentation describes current
behavior.

dStack is stateless with respect to workflow. Do not add a task database, phase detector, readiness calculation, branch
registry, worktree registry, commit map, or coordination protocol.

## Workflow scope

The dStack workflow is opt-in. Do not infer activation from `.beads`, installed skills, or the availability of `bd`.
Only use Beads and the dStack feature workflow when the user explicitly invokes `/plan-feature`, `/review-plan`,
`/implement`, `/close-feature`, or `/audit-project`, or explicitly asks to use dStack. An explicitly requested dStack
command may perform
its documented deterministic mechanics, but it does not activate workflow tracking or create issues.

For all other requests:

- do not run `bd`, including `bd prime` and `bd ready`;
- do not create, update, claim, or close Beads issues; and
- do not require Beads initialization or the dStack formula.

## dStack workflow

When explicitly activated, use the `dstack-feature` molecule:

```text
plan -> review -> human approval -> implementation children -> close
```

Query Beads for the next task. Never calculate readiness or override a Beads blocker.

Planning records the request, questions, answers, decisions, rationale, acceptance criteria, and documentation impact in
Beads. Ask the user about material product, architecture, operational, security, or compatibility decisions before
closing the plan.

Review compares the plan with current code, tests, documentation, and decisions. It creates bounded implementation
tasks and
real dependencies, then presents the reviewed scope for explicit approval.

Implementation claims one ready implementation task. Code, tests, configuration, and current documentation for that
outcome
belong together. Close reviews approved intent before claiming the close step, returns defects to implementation, and
writes feature documentation only after review passes. Project audit creates a normal remediation plan and returns
it for review.

## Deterministic mechanics

dStack commands may:

- initialize and verify project workflow policy;
- enforce feature branch and worktree policy;
- validate plan and task structure;
- create Conventional Commits with Beads evidence;
- inspect reachable Git evidence;
- validate feature documentation; and
- collect bounded close and project-audit facts.

Skills perform semantic judgment and Beads mutations. The CLI does not choose workflow steps or close Beads
work.

## Memory

`/review-plan` and `/audit-project` may search and recall focused Beads memories. `/close-feature` may propose a
reusable
memory write, correction, or retirement, but must receive explicit user approval before mutation. Current repository
documentation and accepted decisions outrank stale memory. Memory is never live workflow state.

## Documentation

Documentation is current product information for users, developers, and future agents. Record current behavior,
interfaces, invariants, tests, and durable rationale in the canonical book. Do not mirror live task status, claims,
readiness, branches, worktrees, commits, or next actions in Markdown.

## Validation

Use the repository checks while working:

```bash
uv run pytest
uv run pytest tests/acceptance
hk check -a
```

Keep generated Beads runtime data out of implementation changes. Preserve deterministic JSON output, focused functions,
Beads operations, and real-Beads acceptance coverage for workflow behavior.
