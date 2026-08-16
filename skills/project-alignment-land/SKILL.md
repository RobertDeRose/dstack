---
name: project-alignment-land
description: Execute Tier 3 final reconciliation, validation, review, and explicitly authorized delivery of a project-alignment molecule.
---

# Project alignment land

Read the dstack core skill and every core reference before acting.

This is Tier 3. Use the user's input as an audit selector and optional delivery
mode: `ready`, `pr`, or `merge`. Default to `ready`.

## Resolve and resume

1. Run the setup doctor.
2. Resolve the audit root and stable steps.
3. Resolve and verify the Beads-managed audit worktree.
4. Inspect native progress for the corrections workstream and audit root.
5. If required corrections remain open, stop and report them.
6. If all required corrections are complete but the corrections epic is open,
   verify progress and close it.
7. Require the landing step to be ready and claim it atomically. If it is already
   closed, resume from the delivery-ready audit root.

## Tier 3 landing work

When the landing step is open:

1. reconcile the approved Tier 1 plan, integrated corrections, specifications,
   reader docs, tests, Beads findings/decisions, and target-branch history;
2. resolve only bounded integration defects implied by approved work;
3. update/rebase the audit candidate onto the current target when required;
4. stop for unresolved conflicts that require new product or architecture
   intent;
5. run final repository validation and all required landing-stage evidence;
6. create one final reconciliation commit when source/docs changed;
7. run the shared integration review loop against the committed candidate;
8. correct findings and rerun validation;
9. add a durable Markdown summary to the landing Bead;
10. close the landing step when the candidate is approved or carries a permitted
    explicit accepted risk.

The audit root remains open after landing preparation. Do not create a separate
landing coordinator or pipeline-state document.

## `ready`

- leave the audit root open;
- comment with candidate commit, target, validation, review outcome, and pending
  delivery evidence;
- optionally label it `dstack:delivery-ready`;
- perform no PR or merge action.

## `merge`

The explicit `merge` argument authorizes a fast-forward delivery attempt.

1. verify/revalidate the candidate against current target history;
2. verify the target worktree is clean;
3. run `git merge --ff-only <audit-branch>`;
4. stop rather than creating a merge commit when fast-forward is impossible;
5. close the audit root only after the target contains the candidate;
6. remove the delivery-ready label and record the delivered commit.

## `pr`

The explicit `pr` argument authorizes PR preparation.

1. present the proposed title/body and require explicit approval unless already
   supplied completely by the user;
2. push and create the PR non-interactively after approval;
3. create a native `gh:pr` gate blocking the audit root, keyed by PR number;

   ```bash
   bd gate create --type gh:pr --blocks <audit-root-id> \
     --await-id <pr-number> --reason "Await merged alignment PR" --json
   ```
4. comment with PR URL and gate ID;
5. leave the root open.

On later invocations, use `bd gate check`. If the gate remains open, report it.
If it confirms merge, verify the target contains the candidate and close the
audit root. Do not implement a custom PR-state poller.

## Cleanup

After actual delivery, use `bd worktree remove` and retain the worktree whenever
native safety checks report uncommitted, unpushed, or stashed work.

## Return

- audit and native progress;
- final reconciliation, validation, review, and commit;
- delivery mode and candidate;
- fast-forward or PR/gate result;
- root closure state;
- worktree cleanup;
- exact next action when delivery remains pending.
