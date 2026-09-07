# Recovery

Beads is the workflow authority and Git is the repository authority. Recovery reads their native state; dStack has no
phase journal, commit map, lease database, or replay protocol.

## Interrupted sessions

Enter the feature worktree with `dstack worktree --bead <root>`. Its reuse does not require merging every subsequent
base-branch change. Inspect `git status`, the selected issue with `bd show <task> --include-comments --json`, and native
workflow position with `bd mol current <root> --json`. For a large graph, prefer `bd mol progress` and a focused
`bd list --parent <implementation> --status in_progress --label dstack:work:implementation --limit 0 --json` query.

Resume work owned by the current agent before calling `bd ready --claim`. Ready work excludes in-progress tasks. Never
steal another claim. One writer may edit or stage in a feature worktree at a time; the CLI mutation lock protects only
individual deterministic commands, not an agent's entire editing session.

## Commit retries and corrections

`dstack commit --bead <task>` is a no-op when the canonical commit already matches the notes and there are no changes.
An updated title or notes can reword an unpublished canonical commit from a clean worktree. Staged corrections rewrite
only the selected owning commit and replay descendants; unrelated pending fixups are not autosquashed.

If rebase stops, use `git status` and native `git rebase --continue` or `git rebase --abort`. Do not invoke another
dStack commit during the operation. An aborted rebase retains the correction commit: inspect it and recover deliberately
before retrying. Do not reset away unrelated work. Published commits and ambiguous ownership are not rewritten.

Keep current delivered outcomes in task notes, review findings and correction rationale in comments, and durable
repository rationale in linked decision Beads. Obsolete notes must not remain as false claims in an amended commit.

## Interrupted close

Repeat semantic review against the approved plan and relevant accepted decisions. Resume an owned in-progress final
step instead of claiming it again. Enter its registered feature worktree before exporting documentation. Re-run
`dstack docs export-design --bead <root> --scaffold` to recreate missing structure without replacing existing prose.
Run documentation validation and `dstack audit --bead <root> --include-plan --require-docs` before closing the
implementation epic, final step, and root in that order. Skip already-closed steps; inspect status rather than inferring
completion from an empty ready queue. Merge and push require separate authorization.

## Resource installation

If resource installation cannot fully restore its previous files, the error reports retained recovery-copy locations. Do
not delete that directory until its previous resources have been restored or deliberately retired. A normal install or
complete rollback removes temporary copies. Initialization updates existing native state rather than pouring or
recreating feature molecules.
