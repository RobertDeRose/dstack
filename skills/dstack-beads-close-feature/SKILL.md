---
name: dstack-beads-close-feature
description: "Claim the native closeout step, reconcile and review the feature, then leave it ready or deliver it by approved PR or fast-forward merge."
---

# Close feature

Read the `dstack-beads-core` skill and every core reference before acting.

Use the user's input as a feature selector and optional delivery mode:
`ready`, `pr`, or `merge`. Default to `ready`.

## Resolve and resume

1. Run the setup doctor.
2. Resolve the feature root and all stable steps, including the closed
   implementation-approval milestone.
3. Resolve and verify the Beads-managed feature worktree.
4. Inspect `bd mol current` and `bd mol progress` for both the implementation
   workstream and feature root.
5. If required implementation children remain open, stop and report them.
6. If all required children are complete but the implementation epic is open,
   verify progress and close it.
7. Require the closeout step to be ready, then claim it atomically. If it is
   already closed, resume from the delivery-ready root instead of creating or
   reopening ceremony work.

## Closeout work

When the closeout step is open:

1. compare accepted design, implementation, tests, reader/operator docs, Beads
   decisions/findings, and actual behavior;
2. reconcile documentation and any bounded closeout defects;
3. run feature-level and repository-required validation;
4. verify all accepted external-validation obligations for this stage;
5. create one closeout candidate commit when source/docs changed;
6. run the shared review loop against the final committed candidate;
7. correct findings and revalidate;
8. add a durable Markdown review/validation comment to the closeout Bead;
9. close the closeout step when the candidate is approved or carries a permitted
   explicit accepted risk.

The poured feature root remains open after closeout. This is the native
`delivery-ready` state; do not create a delivery coordinator issue.

## `ready`

When mode is `ready`:

- leave the feature root open;
- add a concise root comment containing the candidate commit, target branch,
  validation, review result, and any delivery-stage validation;
- optionally add a `dstack:delivery-ready` label as a query aid;
- do not open a PR or merge.

## `merge`

The explicit `merge` argument authorizes a fast-forward delivery attempt.

1. update the feature candidate onto the current recorded target branch when
   necessary;
2. resolve conflicts only when accepted design and completed work determine the
   result; otherwise stop;
3. rerun final validation and review after a rebase;
4. verify the target worktree is clean;
5. run `git merge --ff-only <feature-branch>` from the target worktree;
6. stop rather than creating a merge commit when fast-forward is impossible;
7. close the feature root only after the target branch contains the candidate;
8. update the roadmap entry to `completed` and remove the delivery-ready label.

## `pr`

The explicit `pr` argument authorizes preparing a PR, not silently choosing its
message.

1. update/revalidate the candidate against the current target branch;
2. present the proposed PR title and body;
3. require explicit approval unless the user already supplied the complete
   approved title and body;
4. push the branch and create the PR non-interactively;
5. create a native `gh:pr` gate that blocks the feature root and uses the PR
   number as its await identifier;

   ```bash
   bd gate create --type gh:pr --blocks <feature-root-id> \
     --await-id <pr-number> --reason "Await merged feature PR" --json
   ```
6. add the PR URL and gate ID as a root comment;
7. leave the root open.

On a later invocation, run `bd gate check`. If the PR gate is still open, report
and stop. If it confirms merge, verify the target contains the candidate, close
the feature root, and update the roadmap to `completed`. Do not implement a
dstack PR polling loop.

## Cleanup

Use `bd worktree remove` only after actual delivery and only when its native
safety checks pass. Preserve any worktree with uncommitted, unpushed, or stashed
work.

## Return

- feature and native progress;
- closeout reconciliation, validation, review, and commit;
- delivery mode and candidate;
- root state;
- PR/gate or fast-forward result when applicable;
- roadmap update;
- worktree cleanup result;
- exact next action when delivery remains pending.
