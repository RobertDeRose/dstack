# Worktrees and delivery

Use Beads' native Git worktree commands. dstack does not own a worktree manager.

## Feature worktree

Default branch:

```text
feat/<feature-slug>
```

Before creation, verify the intended base branch exists and resolve its commit.
Use a unique Beads worktree name and the native commands:

```bash
bd worktree list --json
bd worktree create <worktree-name> --branch feat/<feature-slug> --json
bd worktree info --json
```

If the branch must be created from a specific base and Beads does not create it
at that commit, create the branch explicitly with Git first, then let Beads add
the worktree. Never switch the caller's branch merely to create another
worktree.

After creation or reuse, verify with Git:

```bash
git -C <worktree-path> rev-parse --show-toplevel
git -C <worktree-path> branch --show-current
git -C <worktree-path> rev-parse HEAD
```

All source mutations run with the authoritative worktree path as their working
directory.

## Audit worktree

Use a dedicated branch such as:

```text
audit/<audit-slug>
```

Create it only when Tier 2 begins. Tier 1 is read-only and does not need an
execution worktree.

## Removal

Use `bd worktree remove` so Beads applies its safety checks. Never remove a
worktree containing uncommitted, unpushed, or stashed work merely to clean up a
workflow.

## Delivery

`ready` prepares a candidate and leaves the molecule root open.

`merge` means:

- update/rebase the candidate onto the current target when required;
- rerun final validation;
- perform a fast-forward-only merge;
- close the molecule root only after the target contains the candidate.

`pr` means:

- present the proposed title and body for explicit approval;
- create the PR only after approval;
- create a native `gh:pr` gate that blocks the molecule root;
- use `bd gate check` on later invocations;
- close the root only after the gate confirms the PR merged.

Do not create merge commits, force-push shared history, or infer delivery from a
local branch name.
