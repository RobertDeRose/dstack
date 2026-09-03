# dStack agent contract

## Authorities

When the dStack workflow is active, Beads owns plans, decisions, tasks, dependencies, gates, claims, readiness, and
completion. Git owns repository content, branches, worktrees, and history. Repository documentation describes current
behavior.

dStack is stateless with respect to workflow. Do not add a task database, phase detector, readiness calculation, branch
registry, worktree registry, commit map, or coordination protocol.

## Workflow scope

The dStack workflow is opt-in. Do not infer activation from `.beads`, installed skills, or the availability of `bd`.
Only use Beads and the native dStack workflow when the user explicitly invokes `/plan-feature`, `/review-plan`,
`/implement`, or `/audit-feature`, or explicitly asks to use dStack. An explicitly requested `dstack ctl` command may
perform its documented deterministic mechanics, but it does not activate workflow tracking or create issues.

For all other requests:

- do not run `bd`, including `bd prime` and `bd ready`;
- do not create, update, claim, or close Beads issues; and
- do not require Beads initialization or the dStack formula.

## dStack workflow

When explicitly activated, use the native `dstack-feature` molecule:

```text
plan -> review -> human approval -> implementation children -> audit
```

Query Beads for the next task. Never calculate readiness or override a native blocker.

Planning records the request, questions, answers, decisions, rationale, acceptance criteria, and documentation impact in
Beads. Ask the user about material product, architecture, operational, security, or compatibility decisions before
closing the plan.

Review compares the plan with current code, tests, documentation, and decisions. It creates bounded native tasks and
real dependencies, then presents the reviewed scope for explicit approval.

Implementation claims one native ready task. Code, tests, configuration, and current documentation for that outcome
belong together. Audit compares the approved intent with the delivered repository and records any resulting work or
question in Beads.

## Deterministic mechanics

`dstack ctl` may:

- install and verify the project formula;
- enforce feature branch and worktree policy;
- validate plan and task structure;
- create Conventional Commits with Beads evidence;
- inspect reachable Git evidence;
- validate current documentation; and
- collect bounded audit facts.

Skills perform semantic judgment and native Beads mutations. The CLI does not choose workflow steps or close Beads
work.

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
native Beads operations, and real-Beads acceptance coverage for native behavior.
