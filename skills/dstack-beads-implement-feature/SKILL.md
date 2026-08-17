---
name: dstack-beads-implement-feature
description: "Claim and implement native ready work from a feature's implementation molecule, one task at a time by default."
---

# Implement feature

Read the `dstack-beads-core` skill and every core reference before acting.

Use the user's input as an optional feature selector, optional task selector, and
optional `--all`. Default to one implementation task.

When the user supplies no feature selector, resolve the feature in this order:

1. use the exact feature root most recently resolved by `/start-feature` in the
   current Pi session;
2. otherwise, use the feature most recently resolved by
   `/review-feature-spec` in the current Pi session;
3. otherwise, if the current Git worktree is on `feat/<slug>`, resolve the one
   current dstack feature whose root metadata/branch matches that branch;
4. otherwise, if the current worktree path exactly matches one current feature
   root's recorded worktree path, use that feature;
5. otherwise stop and show viable implementation-ready feature roots instead of
   guessing.

An explicit feature selector always overrides these defaults. Do not persist an
"active feature" label or custom state file. A task selector never changes the
active feature.

## Preconditions

1. Run the setup doctor.
2. Resolve the feature root and stable steps through Beads JSON using the
   selector/default rules above.
3. Verify the implementation-approval milestone is closed and its human gate is
   resolved. If either is incomplete, route to `/review-feature-spec`; never
   recommend migration.
4. Resolve the Beads-managed `feat/<slug>` worktree and verify it exactly.
5. Run the deterministic evidence check from the feature worktree:

   ```bash
   python3 "{baseDir}/../dstack-beads-core/scripts/git_evidence.py" \
     --root <feature-worktree> \
     --bead <specification-step-id> \
     --path <design-path>
   ```

6. Require `status: ok`. Missing evidence means the accepted specification was
   never committed with its Beads footer; `status: drifted` means the design
   changed after approval and routes back to `/review-feature-spec`. Do not
   repair either case by writing a commit SHA into Beads.
7. Stop for unrelated dirty changes that would be overwritten, mixed into the
   selected task commit, or make review evidence ambiguous.

## Select and claim native ready work

Without a named task, use the implementation workstream directly:

```bash
bd ready --mol <implementation-workstream-id> \
  --exclude-type epic \
  --claim \
  --json
```

When the user names a task:

1. show it as JSON;
2. verify it belongs beneath the implementation workstream;
3. verify it appears in `bd ready --mol <implementation-id> --json`;
4. claim it atomically with `bd update <task-id> --claim`.

If nothing is ready, use `bd mol current` and `bd mol progress` to report actual
blockers. Do not require metadata from closed tasks or construct a readiness
projection.

If every required implementation child is complete, verify the workstream
progress and close the implementation epic. The formula's closeout task should
then become ready through native dependencies and dynamic fan-in; recommend
`/close-feature <slug>`.

## Implement the selected task

1. Read only the selected Bead, direct blockers, accepted design sections,
   affected code/docs/tests, and evidence required to implement safely.
2. Resolve code questions from repository evidence. A genuine need to change
   accepted intent is `decision required` and routes back through specification
   review; an implementation defect does not.
3. Implement the smallest correct change satisfying the acceptance criteria.
4. Reconcile user/operator documentation in the same task when behavior changes.
5. Run focused validation appropriate to the task. Run broad validation only
   when repository policy or cross-cutting risk requires it.
6. Create one task-sized candidate commit with footer `Beads: <task-id>` unless
   the user explicitly requested a dry run or no commit.
7. Run the shared review loop against the committed candidate.
8. Correct actionable findings, rerun validation, and safely amend the private
   task commit when the boundary remains the same.
9. Ask before a third or later independent review. When authorized, run it; no
   workflow state may refuse.
10. Write a concise review/validation summary to a temporary Markdown file and
    add it with `bd comments add <task-id> -f <file>`.
11. Close the task only after approval, permitted accepted risk, or an explicit
    policy that defers named validation to feature close or delivery.

## Discovered work

Apply the core discovery policy:

- in-scope correctness work stays in the task;
- a small incidental follow-up becomes `bd todo add` plus `discovered-from`;
- significant separate work becomes a fully specified Bead;
- unrelated discoveries do not block the current task.

## External validation

Classify validation by stage:

- task-level evidence blocks this task;
- feature-close evidence blocks closeout only;
- release/environment evidence blocks delivery only when accepted design permits
  implementation to continue.

An aarch64, hardware, CI, or deployment check must not block unrelated work
unless the Beads graph explicitly makes it a prerequisite.

## Continue or stop

Without `--all`, stop after one task.

With `--all`, repeat serially until no task is ready, a real decision is needed,
required task-level validation cannot run, the worktree boundary is unsafe, or
the user interrupts. Phase 1 does not launch parallel writers even though Beads
correctly exposes independent work as parallel-ready.

After each task, inspect native progress. Close the implementation epic only
when all required children are complete or explicitly deferred/accepted.

## Return

- feature, worktree, and specification evidence status;
- selected/claimed task;
- behavior and files changed;
- validation and pending stage-specific evidence;
- review findings, corrections, and extra-review authorization;
- task commit and Beads review/validation comment;
- task closure and native molecule progress;
- currently ready and blocked work;
- exact next command.
