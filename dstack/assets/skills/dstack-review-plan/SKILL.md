---
dstack-managed: true
name: dstack-review-plan
description: "Reconcile a completed feature plan with memory and repository facts, then create its native task graph."
disable-model-invocation: true
---

# Review plan

Run only when explicitly invoked. Beads owns the graph, dependencies, approval gate, and ready frontier.

## Review

1. Resolve the feature and claim only its `dstack:step:review` step.
2. Search `bd memories <focused terms> --json`, then recall only relevant keys. Memory is advisory: current repository
   documentation and accepted feature decisions outrank stale memory.
3. Inspect only relevant source, tests, current documentation, and decisions.
4. When useful, review independently from implementation, documentation, and risk perspectives, then store only the
   synthesized findings in Beads.

Correct clear plan defects. Ask the user when repository facts, accepted intent, and memory leave material authority
ambiguous. With user approval, correct or retire stale memory; never use memory as live workflow state.

Record durable decisions as native decision Beads labeled `decision:<slug>` and connect each decision to the feature
root with an exact `relates-to` dependency.

## Create implementation work

Create bounded task-shaped outcomes directly under the implementation epic. Each task needs:

- `dstack:work:implementation` and no inherited structural label;
- a `description` containing the planned outcome, scope, and non-goals, not commit prose;
- a `design` containing the accepted approach, invariants, and boundaries;
- observable `acceptance_criteria` describing the behavior that proves completion;
- real `blocked-by` dependencies, including a direct blocker on the approval step.

Leave execution `notes` empty until implementation begins. Agents append one concise, verb-led
`Implementation: <completed increment>` fragment per meaningful delivered increment. Keep each fragment to one concrete
change, preferably one line and no more than 96 characters. dStack strips surrounding whitespace and punctuation, then
adds a dash-and-space prefix without wrapping. Only those ordered notes become canonical commit bullets;
`No repository change: <specific reason>` is reserved for intentional no-change tasks.

Do not add commit-type or scope labels. Add task ordering only where execution order is real. Do not add direct
readiness edges to the final step; the formula supplies implementation fan-in and its fixed close-review gate.

Run:

```bash
dstack check plan --bead <plan>
dstack check review --feature <root>
```

No implementation task may be ready before approval, and the native graph must be cycle-free. Close the review only
after checks pass, then present scope, risks, decisions, and the task graph. Review never grants approval.

After explicit user approval, resolve only the formula gate with await ID `approve-<slug>-plan`, claim and comment on
the approval step, close it, and return `/implement <root>`.
