---
name: implement-feature
description: Implement or continue the next ready task in a reviewed Beads feature while keeping code, tests, documentation, evidence, and commits aligned. Use when asked to implement feature work after `start-feature` closes `spec-reconcile`.
metadata:
  version: "0.8.3"
allowed-tools: Read Glob Grep Edit Write Bash Task AskUserQuestion
---

# Purpose

Use this skill after `/start-feature` closes `spec-reconcile`. Accept the same human feature selectors as
`/start-feature`. Beads selects executable work; `design.md` supplies intended behavior and design constraints. Resolve
`<core-dir>` as the installed `../dstack-core` skill directory. If the supplied selector resolves to a standalone
`task`, `bug`, `chore`, `spike`, or `feature` rather than a child of a reviewed `workflow:feature` epic, stop before
claiming it and recommend `/implement-task <human task selector>`.

## Startup version evidence

Before claiming a child or mutating the feature, follow
[`../dstack-core/references/SKILL-VERSION.md`](../dstack-core/references/SKILL-VERSION.md) for `implement-feature`.
After read-only feature resolution, capture the exact one-line output and append it to the selected root or child Beads
notes before the claim. A `stale` result warns with `npx skills update`; `unavailable` records that no freshness claim
was made and does not block offline work.

## Execution

## 1. Load Minimal Context

Run `bd prime`, then resolve the supplied feature selector. When the selector is omitted, use this deterministic
precedence:

1. the current branch when it matches `feat/<slug>`;
2. the repository-local feature recorded by the last successful `/start-feature`;
3. otherwise stop and require a selector rather than choosing unrelated ready work.

```bash
branch=$(git branch --show-current)
if [[ "$branch" == feat/* ]]; then
  feature_selector=${branch#feat/}
else
  feature_selector=$(git config --get dstack.activeFeature || true)
fi
test -n "$feature_selector"
uv run <core-dir>/scripts/resolve-feature.py "$feature_selector" --json
bd show <resolved-root-id> --json
```

Never use automatic next-feature selection here. Validate the stored value through the resolver exactly like a
user-supplied selector; stale or ambiguous state must stop rather than select a different feature.

Use the returned root ID only for Beads operations and the returned `<slug>` reference for worktree, reporting, and
continuation commands. Resolve the implementation coordinator from root metadata `implementation_id`. Query the feature
children only as a one-time metadata repair path. This keeps the normal context load independent of total feature size
and works for both molecules and migrated parent-child lifecycles. Activate and verify `feat/<slug>`.

Select a user-specified task first when provided; otherwise atomically claim the next ready child:

```bash
bd ready --parent <implementation-id> --claim --json
bd show <task-id> --json
```

This selects the next work unit, not the end of the invocation. After closing each child, immediately return to this
selection step and continue the same feature.

Read structured metadata, scope, acceptance criteria, blockers, design references, documentation ownership, and
validation before loading more files. Read only the relevant design sections and reader-facing pages unless broader
context is required.

Legacy `tasks.md` files are migration input only. Never use them as live task state after Beads import.

## 2. Implement the Bounded Outcome

Before mutating code, run a semantic boundedness check against the selected child and reviewed design. The child must
identify one independently reviewable behavior, one primary owner, and one practical commit boundary. Character counts
are warning signals only, not correctness limits. If the child combines independent outcomes, ownership boundaries,
documentation sets, or commit boundaries, do not write code: record the planning defect, reopen `spec-reconcile`, and
return the task to specification reconciliation rather than inventing a decomposition during implementation.

Material planning changes discovered at any point also stop implementation. Material changes to behavior, ownership,
compatibility, or acceptance stop implementation and invalidate the reviewed source boundary: reopen `spec-reconcile`
and the affected review beads, mark stale review evidence as invalid, reconcile the design and task acceptance, commit
and review the new specification boundary, and reclaim implementation only after its gates close. Do not reconcile
material intent in place or continue under old review evidence. An editorial clarification is allowed in place only when
it does not alter reviewed intent, ownership, compatibility, acceptance, or the review boundary; record the
clarification and continue.

Implement the smallest complete change satisfying the selected task. Preserve the reviewed design and established
repository patterns. Keep code, tests, configuration, migrations, observability, failure behavior, and recovery within
the task boundary.

Update the exact reader-facing pages assigned to the task. Add other pages only when delivered behavior creates a
durable reader need. Register each new page in `docs/src/SUMMARY.md` in the same work unit. Feature designs remain
published audit records, but product documentation must stand alone without requiring them.

## 3. Validate and Review

While iterating, run the smallest focused checks that cover the changed behavior. After the scoped implementation and
review fixes stabilize, run task-specific validation, `uv run scripts/check-docs.py` when documentation changes, and the
full repository-standard suite once before commit. Rerun the full suite only when it failed or a subsequent fix affects
broad/shared behavior; otherwise rerun only impacted focused checks.

Launch exactly one initial reviewer with `context: fresh`, focused on correctness, security, maintainability, test
adequacy, and compliance with the selected task and design. A separate context builder is unnecessary for this single
scoped reviewer. Follow `../dstack-core/references/REVIEW-STATE.md` and `../dstack-core/references/REVIEW-FINDINGS.md`
to persist the review bead's run ID, reviewer session, packet identity/digest, reviewed commit/diff boundary, current
disposition, and current open findings before launch. Do not add confidence reviewers without a distinct uncovered risk
or an explicit user request.

Resolve actionable findings. Resume the same reviewer and run ID to verify fixes. Use a fresh replacement only if the
original cannot be resumed; if a fix materially changes the reviewed scope, stop and use the planning-defect path above
rather than asking a replacement reviewer to approve a different boundary. Provide a replacement the original packet
identity, findings ledger, resolutions, and post-review diff. Record the unavailable/replacement reason and current
`Review state:` record alongside commands, outcomes, limitations, findings, and fixes:

```bash
bd update <task-id> --append-notes "Validation and review evidence: ..."
```

## 4. Commit and Close

Run `git status --short`; identify pre-existing or out-of-scope changes and exclude them from the task boundary.

When the task changes the repository:

1. commit the complete bounded outcome;
2. include the Beads task ID in the commit message;
3. capture the exact commit SHA with `git rev-parse HEAD`;
4. record that SHA in the task notes before closure.

```bash
commit_sha=$(git rev-parse HEAD)
bd update <task-id> --append-notes "Commit evidence: ${commit_sha}"
bd close <task-id> --reason "Acceptance criteria satisfied; commit ${commit_sha}"
```

When the task legitimately requires no repository change, verify that no intended task change is uncommitted and record
an exact reason before closure:

```bash
bd update <task-id> --append-notes "Commit evidence: no commit required — <specific reason>"
bd close <task-id> --reason "Acceptance criteria satisfied; no commit required — <specific reason>"
```

Do not close a task with a placeholder SHA, an omitted commit field, or the unexplained phrase `no commit required`.
Every closed implementation task must have either a real commit SHA or a specific no-commit justification.

Record out-of-scope discoveries with provenance:

```bash
bd create "<discovered work>" \
  --type <bug|spike|chore|task> \
  --deps discovered-from:<task-id> \
  --json
```

Use `bug` for a defect, `spike` for bounded fact-finding with exit criteria, `chore` for maintenance, and `task`
otherwise. Do not create an implementation `decision` to defer unresolved product policy; return that gap to
specification reconciliation. Add a blocking edge only when the discovered issue is a true prerequisite for safe
completion.

## 5. Continue Until the Feature Is Exhausted

A task boundary or commit boundary is not a stopping point. Before claiming the next child after every successful child
commit and closure, run a cohesion checkpoint against new evidence from implementation, review, and validation. Look
specifically for new ownership boundaries, migrations, external dependencies, or risky effect classes. If no independent
value or review boundary is found, continue under the same feature. Incidental complexity alone is not a decomposition
signal.

When the evidence identifies independently valuable and reviewable remaining outcomes, pause the implementation
coordinator and record the cohesion defect and its provenance. Do not create replacement children or new epics from the
implementation loop, and do not continue claiming remaining work under an incoherent coordinator. Return through normal
feature planning authority to define dependent feature epics, preserve user authority and existing Beads dependency
semantics, and run the required design/review gates before implementation resumes. Preserve completed work and add
`blocks` edges only for real prerequisites.

When the checkpoint confirms cohesion:

1. query and atomically claim the next ready child under the same implementation coordinator;
2. implement, validate, review, commit, and close it;
3. repeat while any implementation child remains open.

When no child is ready, inspect every open child and its blocking edges. Resolve non-decision blockers, stale dependency
state, or graph defects and continue. For externally running prerequisites, coordinate and wait rather than duplicating
or abandoning them; for transient external failures, retry while completing any other ready feature work. Unavailable
required validation becomes a user decision only if a waiver is needed. Do not stop because one task is blocked while
another is ready.

Pause for the user only when **every** remaining open child is blocked by missing user decisions; ask one decision
question at a time and resume immediately after each answer. This state is valid only for migrated work: native
`/plan-features` output must already contain every implementation decision.

If implementation exposes a material planning defect involving behavior, ownership, compatibility, acceptance, or a new
independent boundary, stop and follow the planning-defect invalidation path in Section 2. Do not continue under the old
specification or review evidence. If the discovery is only an editorial clarification that leaves reviewed intent
unchanged, record it and continue. Native `/plan-features` output should prevent both cases, but the gate protects
against drift discovered during implementation.

## 6. Complete the Implementation Coordinator

After all required children are closed or explicitly deferred, compare delivered behavior with `design.md`, run
implementation-level acceptance checks, record evidence, and close the implementation coordinator:

```bash
bd update <implementation-id> --append-notes "Implementation acceptance evidence: ..."
bd close <implementation-id> --reason "Required implementation work complete; acceptance verified"
```

Clear stale default selection after the coordinator closes, but only when it still names this feature:

```bash
test "$(git config --get dstack.activeFeature || true)" != "<slug>" || \
  git config --unset-all dstack.activeFeature
```

Return only after the implementation coordinator closes, or when every remaining child is simultaneously blocked on
explicit user decisions. Report the canonical feature reference and human name, all completed task IDs and commits,
worktree, changes, documentation, validation, reviews, discovered work, coordinator state, and next lifecycle item.
Always include a `Recommended next step` line:

- when the implementation coordinator closed successfully, recommend `/close-feature <slug>`;
- when paused for decisions, state that implementation is blocked, name the blocker category, and ask only the next
  decision question;
- when blocked by validation, review, environment, dependency, or repository-state issues, state the exact advisement or
  approval needed before `/implement-feature <slug>` can resume.

Do not end with only a status summary. The recommendation must make clear whether the feature is ready for close-out or
whether user advisement is needed first.
