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
2. Verify `.beads/interactions.jsonl` is not tracked by Git. If it is tracked,
   stop before delivery mutations and instruct the user to run
   `/setup-project --force` once from the repository's main worktree. Preserve
   the file; never restore or commit it as feature bookkeeping.
3. Resolve the feature root and all stable steps, including the closed
   implementation-approval milestone.
4. Resolve and verify the Beads-managed feature worktree.
5. Inspect `bd mol current` and `bd mol progress` for both the implementation
   workstream and feature root.
6. If required implementation children remain open, stop and report them.
7. If all required children are complete but the implementation epic is open,
   verify progress and close it.
8. Require the closeout step to be ready, then claim it atomically. If it is
   already closed, resume from the delivery-ready root instead of creating or
   reopening ceremony work.

## Closeout work

When the closeout step is open:

1. compare accepted design, implementation, tests, reader/operator docs, Beads
   decisions/findings, and actual behavior;
2. reconcile durable product/developer/user documentation and any bounded
   closeout defects. Implemented-feature records may explain what was added, why,
   and how it works, but must not contain workflow status, Beads IDs, branch
   names, commit IDs, or next-command bookkeeping;
3. run feature-level and repository-required validation;
4. verify all accepted external-validation obligations for this stage;
5. create one closeout candidate commit with footer `Beads: <closeout-step-id>`
   when source/docs changed;
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
- add a concise root comment containing the target branch, validation, review
  result, and any delivery-stage validation; do not copy a Git SHA into Beads;
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
7. close the feature root only after the target branch contains the delivered
   feature history;
8. remove the delivery-ready label;
9. make no repository changes after the merge. Delivery-state changes belong in
   Beads only.

## `pr`

The explicit `pr` argument authorizes preparing a PR, not silently choosing its
message. A PR delivers the **whole feature branch**, not merely the final
closeout commit.

1. Resolve the current recorded target branch from the local target worktree.
   Fetching `origin` may refresh remote state, but `origin/<target>` is not a
   substitute for the recorded local target branch. If local target and remote
   target differ, report that explicitly before proposing or creating the PR.
2. Update/revalidate the candidate against the current recorded target branch.
3. Before drafting the PR, inspect the complete feature delta from target to
   candidate, including both the commit series and aggregate diff:

   ```bash
   git -C <feature-worktree> log --oneline --no-merges <target>..HEAD
   git -C <feature-worktree> diff --stat <target>...HEAD
   git -C <feature-worktree> diff --name-status <target>...HEAD
   ```

4. Draft the PR title from the delivered feature as a whole. Do not derive the
   title from the closeout commit subject merely because it is `HEAD`.
5. Draft the PR body from the whole feature delta. Summarize material product,
   source, configuration, test, and documentation changes represented by
   `<target>...HEAD`; include closeout documentation as one part of that
   summary, not as the feature itself. Include validation and any accepted
   risks or pending delivery-stage checks.
6. Sanity-check the draft against `git diff --stat <target>...HEAD`. A docs-only
   PR title/body is invalid when the feature delta contains non-documentation
   source/config/test changes. Likewise, do not advertise code changes that are
   absent from the aggregate diff.
7. Present the proposed PR title and body.
8. Require explicit approval unless the user already supplied the complete
   approved title and body.
9. Push the branch and create the PR non-interactively.
10. create a native `gh:pr` gate that blocks the feature root and uses the PR
   number as its await identifier;

   ```bash
   bd gate create --type gh:pr --blocks <feature-root-id> \
     --await-id <pr-number> --reason "Await merged feature PR" --json
   ```
11. add the PR URL and gate ID as a root comment;
12. leave the root open.

On a later invocation, run `bd gate check`. If the PR gate is still open, report
and stop. If it confirms merge, verify the target contains the PR head, close the feature
root, and remove the delivery-ready label. Do not edit repository documentation
after merge and do not implement a dstack PR polling loop.

## Cleanup

After any delivery-state Beads mutations, verify the target worktree remains
Git-clean. A modified tracked `.beads/interactions.jsonl` is a repository-hygiene
error, not something to restore or commit; preserve it and require the one-time
`/setup-project --force` migration.

Use `bd worktree remove` only after actual delivery and only when its native
safety checks pass. Preserve any worktree with uncommitted, unpushed, or stashed
work.

## Return

- feature and native progress;
- closeout reconciliation, validation, review, and commit;
- delivery mode and candidate;
- root state;
- PR/gate or fast-forward result when applicable;
- confirmation that no post-delivery Git bookkeeping was created;
- worktree cleanup result;
- exact next action when delivery remains pending.
