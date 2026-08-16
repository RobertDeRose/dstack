---
name: dstack-beads-project-alignment-review
description: "Pour and execute Tier 1 of the native project-alignment workflow: immutable analysis, corrective planning, and an unresolved human gate."
---

# Project alignment review

Read the `dstack-beads-core` skill and every core reference before acting.

This is Tier 1. It analyzes and prepares a durable corrective plan. It does not
modify source, create an execution worktree, implement corrections, or deliver.

Use the user's input as the scope and optional audit name/target branch. Default
the target to `dev` only when that branch exists and no target was supplied.

## Establish the audit

1. Run the setup doctor.
2. Verify the target branch and capture its immutable commit.
3. Search existing open project-alignment roots. Reuse an exact matching audit
   or stop on ambiguity; do not pour duplicate audits for the same intended
   baseline and scope.
4. Resolve a stable audit slug.
5. Pour the persistent proto:

   ```bash
   bd mol pour dstack-project-alignment \
     --var audit_title="<title>" \
     --var audit_slug="<slug>" \
     --var target_branch="<target>" \
     --var baseline_commit="<commit>" \
     --var scope="<scope>" \
     --json
   ```

6. Update the returned root:
   - title `Project alignment: <title>`;
   - labels `workflow:project-alignment` and `audit:<slug>`;
   - external reference `git:<baseline-commit>`;
   - metadata containing slug, target branch, baseline, and scope.
7. Resolve exactly one analysis step, alignment-approval milestone,
   corrections workstream, landing step, and open human gate.
8. Claim the analysis step atomically.

## Read-only analysis boundary

During Tier 1, do not modify source, tests, configuration, reader docs, feature
designs, branches, or worktrees. Beads changes are allowed because the audit
molecule and its dynamic children are the durable execution plan.

Inventory and compare:

- project and feature specifications;
- reader/operator documentation;
- implementation and tests;
- public interfaces, data ownership, and failure paths;
- existing Beads work, decisions, TODOs, and deferred findings;
- Git history and locally available delivery/validation evidence.

Classify findings by real outcome:

- specification drift;
- correctness defect;
- security or privacy concern;
- reliability or operability weakness;
- performance concern;
- maintainability or unnecessary complexity;
- missing/stale documentation;
- missing validation;
- unresolved product/architecture decision;
- already tracked, invalid, or out of scope.

Use concrete evidence. Ask one targeted question at a time when repository
evidence cannot determine intended behavior.

## Build the corrective workstream

Create one bounded child under the corrections epic for every accepted durable
corrective outcome. Every child must:

- use `--no-inherit-labels`;
- carry `dstack:work:alignment` and `audit:<slug>`;
- depend on the alignment-approval milestone;
- state the problem/evidence, required outcome, acceptance criteria, affected
  scope, risk, and expected validation.

Deduplicate existing Beads work. Link an already-tracked issue rather than
creating another. Use dependencies only for genuine execution order; leave
independent corrections unordered.

Use `bd todo add` only for small incidental follow-ups outside the approved
audit plan. Link them with `discovered-from` and keep them nonblocking.

## Complete Tier 1

1. review the proposed corrective graph for completeness, YAGNI, dependency
   correctness, and testability;
2. add a concise executive assessment and plan summary as an audit-root comment;
3. close the analysis step;
4. leave the human gate open and the alignment-approval milestone blocked;
5. verify the corrections remain absent from the ready frontier because they
   depend on that unresolved approval milestone;
6. present the plan and stop for user approval.

Do not begin Tier 2 in the same invocation. The exact approval action is
`/project-alignment-execute <audit-slug>`.

## Resume behavior

When resuming an existing Tier 1 audit:

- preserve resolved decisions and completed analysis;
- update the plan idempotently;
- compare current target history with the recorded baseline;
- ask whether to refresh a materially stale baseline rather than silently
  replacing it;
- never migrate workflow topology.

## Return

- audit root, stable steps, approval milestone, and human gate;
- target branch and immutable baseline;
- executive alignment assessment;
- findings and evidence;
- decisions resolved and still required;
- corrective Beads graph and dependencies;
- validation/landing strategy;
- duplicate, TODO, and out-of-scope findings;
- native molecule progress;
- explicit state `audit plan ready for approval` or the concrete blocker;
- exact `/project-alignment-execute` command only when ready.
