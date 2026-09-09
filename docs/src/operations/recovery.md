# Recovery

Beads remains the workflow authority and Git remains the repository authority after an interruption. dStack does not
keep a phase journal, task cache, commit map, lease database, or replay protocol.

## Interrupted implementation

Locate the feature worktree with:

```text
dstack worktree --bead <feature>
```

If the result is `recovery_required`, enter the returned path and inspect `git status`. Finish or deliberately abort the
reported Git operation before running another mutating dStack command. dStack reports the existing Git state; it does
not repair it automatically.

Inspect the selected task with `bd show <task> --include-comments --json` and the feature with
`bd mol current <root> --json`. For a large feature, use `bd mol progress` and focused `bd list` queries rather than
loading unrelated issues.

Resume work already owned by the current agent before claiming another ready task. Never take another owner's claim.
Only one agent should edit or stage in a feature worktree at a time; dStack's mutation lock protects individual CLI
operations, not the entire editing session.

## Commit retries and corrections

`dstack commit --bead <task>` is a no-op when the canonical commit already matches the task notes and there are no
repository changes. Updated task titles or notes can reword an unpublished canonical commit from a clean worktree.
Staged corrections rewrite only the selected owning commit and replay its descendants; unrelated fixups are not folded
into it.

If a rebase stops, use `git status` and normal `git rebase --continue` or `git rebase --abort`. Do not run another
dStack
commit during the rebase. An aborted correction retains the correction commit so it can be inspected and recovered
deliberately. Published commits and ambiguous ownership are not rewritten.

## Interrupted close

Repeat the semantic close review instead of assuming that an earlier session finished it. Verify that every
implementation child remains a direct blocker of the close step; repair a missing edge before trusting close readiness.
This recovers interruptions between task creation and blocker attachment without creating dStack-owned recovery state.

Resume a close step already owned by the current agent instead of claiming it again. Enter the registered feature
worktree before writing documentation. Re-run:

```text
dstack docs export-design --bead <root> --scaffold
```

to recreate unambiguous missing structure without replacing existing prose.

Before completing close, run the repository's validation and:

```text
dstack check feature --bead <root> --include-plan --require-docs
```

Then close the implementation epic, close step, and feature root in that order, skipping issues already closed. Verify
Beads status rather than inferring completion from an empty ready queue. Merge and push still require separate
authorization.

## Interrupted resource installation

If `dstack install` cannot fully restore the previous agent resources, its error reports the directory containing
recovery copies. Keep that directory until the previous resources have been restored or deliberately retired. A normal
installation or complete rollback removes its temporary copies.
