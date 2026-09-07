---
dstack-managed: true
name: dstack-review-plan
description: "Reconcile a completed feature plan with memory and repository facts, then create its native task graph."
disable-model-invocation: true
---

# Review plan

Run only when explicitly invoked. Beads owns the graph, dependencies, approval gate, and ready frontier.

## Review

1. Resolve the feature with `bd mol current <root> --json`. Read the plan and review step with
   `bd show <plan> <review> --include-comments --json`. Resume this agent's in-progress review without reclaiming it;
   respect other owners. Claim only a native-ready open review. If review is already closed, inspect the existing
   approval state and proceed only with recorded explicit approval; do not recreate tasks or grant approval by inference.
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

First inspect existing implementation children; reconcile partial review work by ID instead of creating duplicate tasks.
Create bounded task-shaped outcomes directly under the implementation epic. Use one native `bd create` invocation with
`--parent`, `--no-inherit-labels`, `--labels`, `--description`, `--design`, `--acceptance`, and `--deps blocked-by:<approval>`
so new work never temporarily lacks its approval blocker. Each task needs:

- `dstack:work:implementation` and no inherited structural label;
- a `description` containing the planned outcome, scope, and non-goals, not commit prose;
- a `design` containing the accepted approach, invariants, and boundaries;
- observable `acceptance_criteria` describing the behavior that proves completion;
- real `blocked-by` dependencies, including a direct blocker on the approval step.

Leave execution `notes` empty until implementation begins. Agents append one concise, verb-led
`Implementation: <completed increment>` fragment per meaningful delivered increment. Keep each fragment to one concrete
change, preferably one line and no more than 96 characters. dStack trims surrounding whitespace, preserves technical punctuation, then
adds a dash-and-space prefix without wrapping. Only those ordered notes become canonical commit bullets;
`No repository change: <specific reason>` is reserved for intentional no-change tasks.

Do not add commit-type or scope labels. A plain task title defaults to `feat`; use a native title such as
`fix: Preserve inbound timestamps` when another conventional commit type is appropriate. Add task ordering only where execution order is real. Do not add direct
readiness edges to the final step; the formula supplies implementation fan-in.

Run:

```bash
dstack check plan --bead <plan>
dstack check review --bead <root>
```

No implementation task may be ready before approval. Let Beads validate dependency legality and readiness, including
cross-feature blockers and native conditional dependencies. Do not reject this feature for unrelated project cycles. Close the review only
after checks pass, then present scope, risks, decisions, and the task graph. Review never grants approval.

After explicit user approval, resolve only the formula gate with await ID `approve-<slug>-plan`, resume this agent's in-progress approval or claim it only when open and ready, record the approval evidence, close it, and return `/implement <root>`.
