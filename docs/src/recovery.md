# Interrupted Skill Recovery

If a workflow command stops partway through its work, resume the feature that already exists instead of starting a
replacement. The sections below cover the common recovery paths.

## Interrupted implementation

Run the implementation workflow again with the same feature or task:

```text
/implement <feature>
```

or:

```text
/implement <task>
```

The implementation skill resumes an in-progress task already owned by the current agent before claiming another ready
task.

If you need to inspect the repository state directly, locate the feature worktree with:

```text
dstack worktree --bead <feature>
```

A normal result gives you the worktree to continue using. If the result reports `recovery_required`, enter that worktree
and inspect `git status` before making more changes.

For workflow state, these Beads commands are useful when diagnosing a stopped session:

```text
bd mol current <feature> --json
bd show <task> --include-comments --json
```

Do not take a task that is already claimed by another agent.

## Commit/rebase recovery

A clean retry of:

```text
dstack commit --bead <task>
```

is safe. If the canonical task commit already matches the task notes and there are no new repository changes, dStack
returns it unchanged.

When a commit correction stops during a rebase, use the normal Git recovery commands from the feature worktree:

```text
git status
git rebase --continue
```

or, when you intentionally want to abandon the rebase:

```text
git rebase --abort
```

Finish or abort the rebase before running another mutating dStack command. If an aborted correction leaves a retained
correction commit, inspect it before deciding whether to reuse or remove it.

## Interrupted close

Run close again with the same feature:

```text
/close-feature <feature>
```

Close repeats its review from current repository and Beads state. It resumes a close step already owned by the current
agent, rechecks implementation work, and continues documentation publication only after the feature is ready to close.

If close reports a Git recovery condition, resolve that Git operation first using the commit/rebase procedure above,
then run `/close-feature <feature>` again.

Closing or merging a feature does not imply permission to push or perform other delivery actions. Those still require
the authorization expected by the target repository.

## Interrupted installation

Run agent-resource installation with:

```text
dstack install
```

Installation restores the previous managed resources automatically when an update fails and rollback succeeds. After a
complete rollback, fix the reported cause and run `dstack install` again.

If rollback cannot restore every previous resource, the error reports a directory containing recovery copies. Keep that
directory, restore or deliberately retire the affected resources, and only then retry installation. A successful
installation removes its temporary recovery copies.

For exact CLI behavior and exit codes, see the [CLI reference](reference/cli.md).
