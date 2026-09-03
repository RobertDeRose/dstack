---
dstack-managed: true
name: dstack-beads-review-plan
description: "Review a completed feature plan against the repository and create the approved native Beads task graph."
---

# Review plan

Review the plan independently before implementation. Beads owns the task graph, dependencies, human gate, and ready
frontier. dStack supplies only structural and repository checks.

## Claim and inspect

1. Resolve the selected feature root and identify its fixed formula steps by label.
2. Claim only the native review step:

```bash
bd ready --parent <root> --label dstack:step:review --claim --json
```

3. Read the completed plan, relevant current source, tests, architecture, operations, development and reference
   documentation, and relevant decision Beads.
4. Review from three independent perspectives when subagents are available: implementation accuracy, current
   documentation/architecture, and plan risk. Persist only synthesized findings in Beads.

## Reconcile the plan

Compare proposed behavior with actual code and current documentation. Identify missing behavior, assumptions,
migrations, failure handling, security boundaries, tests, rollout concerns, documentation effects, and conflicts with
prior accepted decisions.

Correct clear local defects directly in the plan Bead and rerun:

```bash
dstack ctl plan check <plan-bead>
```

When code, documentation, and proposed intent disagree and the authoritative behavior is unclear, ask the user before
changing the plan or task graph. Record the answer and rationale. Create a native `decision` Bead for material durable
choices, label it `feature:<slug>`, and relate it to the feature.

## Create implementation tasks

Create only bounded implementation outcomes under the formula's implementation epic. Each task must:

- have label `dstack:work:implementation`;
- have exactly one `dstack:commit:<type>` label;
- optionally have one `dstack:scope:<scope>` label;
- contain concrete acceptance criteria;
- contain this documentation-impact matrix with a meaningful reason:

```markdown
## Documentation impact

- End-user: required - <what changes and where>
- Developer: required - <what changes and where>
- Future-agent: required - <current invariant or decision record affected>
```

Use `not affected` instead of `required` only with a specific reason. Code, tests, configuration, and the current
documentation describing the behavior belong to the same task.

Create each task and its approval blocker in one native Beads operation:

```bash
bd create '<task title>' \
  --type task \
  --parent <implementation-epic> \
  --no-inherit-labels \
  --labels dstack:work:implementation \
  --labels dstack:commit:<type> \
  --labels dstack:scope:<scope> \
  --deps blocked-by:<approval-step> \
  --description-file <temporary-description> \
  --acceptance '<observable criteria>' \
  --json
```

Omit the scope label when no scope is useful. Add task-to-task `blocked-by` dependencies in the same create operation
when execution order is real. Do not add direct task-to-audit blockers: the formula's native
`children-of(implementation)` waits-for edge is the sole audit fan-in.

After creating tasks, verify observable native behavior before closing review:

```bash
bd ready --parent <implementation-epic> --label dstack:work:implementation --json
bd dep cycles
```

No implementation task may be ready while approval is open. If interrupted, list the existing implementation children
and continue from their concrete IDs; do not recreate an already represented outcome.

Do not add a blocking dependency between the approval task and the implementation epic. Beads 1.2.2 rejects task/epic
`blocks` edges; approval belongs on each task-shaped implementation child.

Close the review step only after the plan and native graph are internally consistent. Then present the reviewed plan,
task graph, risks, and decisions to the user. Invocation is not approval.

## Human approval

Only after explicit user approval:

1. resolve the formula-generated human gate blocking the approval step;
2. claim the now-ready approval step;
3. record the approval scope in a Beads comment; and
4. close the approval step.

Do not store a second pending/approved digest protocol. The native gate and approval-step history are the authorization
record.

Return implementation task IDs and `/implement <root>` as the next action.
