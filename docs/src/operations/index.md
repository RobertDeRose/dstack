# Operations

This section is the operator contract for installing and running dStack. The
[compatibility reference](../reference/compatibility.md) lists the exact supported tool versions.

## Install and configure

1. Install the pinned Python, Beads, mdBook, Git, and `uv` toolchain.
2. Invoke `/setup-project`. Setup emits a read-only plan containing exact filesystem, Git-index, Beads, formula, and
   documentation changes.
3. Review the plan, then let setup apply its digest. Apply recomputes the plan after a clean-worktree preflight and
   refuses changed authority state.
4. Run setup doctor with an explicit delivery profile and resolve every reported diagnostic before feature work:

   ```text
   setup.py doctor --root . --delivery-mode merge
   setup.py doctor --root . --delivery-mode pr
   ```

   Merge mode is local/direct-delivery health and does not require a remote, GitHub, or `gh`; PR mode additionally
   checks a usable GitHub target remote, authenticated `gh`, and native Beads `gh:pr` gate support.

Setup creates only missing documentation foundation files. `--force` is an explicit compatibility boundary for replacing
drifted formulas and applying mechanically identifiable legacy repair. It is not routine startup behavior.

Stable configuration lives in Git and Beads: formula source, `docs/book.toml`, Beads configuration, root metadata
described in the [metadata reference](../reference/metadata-labels.md), and normal Git remotes. The default feature
target is `main`; alignment requires an explicit target and scope. dStack has no database, scheduler, state packet, or
ownership ledger.

## Daily use and concurrency

Use the [command contracts](../reference/cli.md) to plan, authorize, implement, reconcile, and deliver work. Beads is
the sole authority for readiness, dependencies, gates, claims, and completion. Git is the sole authority for content,
worktrees, commits, and delivery history.

Each feature or alignment uses a conventional native Git worktree. Commands refuse missing, duplicated, dirty, or
unexpectedly placed worktrees rather than choosing one heuristically. One writer operates in a worktree at a time.
Native Beads atomic claims arbitrate concurrent workers; a worker cannot complete work claimed by another actor.

Clean completed worktrees with native `git worktree remove` and `git worktree prune` only after delivery and after
confirming no uncommitted files remain. Do not delete Beads/Dolt files to resolve workflow state.

## Upgrade and uninstall

Upgrade only through an explicit compatibility change backed by fast tests and both real-Beads acceptance scenarios.
Review setup plan before applying the new formula bytes. Never run legacy repair as part of an ordinary upgrade.

To uninstall the Pi package, remove its installed package through Pi's package mechanism. Repository-owned formulas,
documentation, Beads history, and Git history remain project data; remove them only through a separately reviewed
repository change. See [recovery](recovery.md) before destructive cleanup.
