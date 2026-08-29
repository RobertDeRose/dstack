# Operations

This section is the operator contract for installing and running dStack. The
[compatibility reference](../reference/compatibility.md) lists supported runtime behavior.

## Install and configure

1. Install the package's locked runtime with `mise --cd <dstack-package-root> install --locked`.
2. Install/reload the Pi package.
3. Run the normal workflow command from the target repository.

There is no setup workflow. Controller entry points preserve the caller repository, initialize Beads when needed, and
silently synchronize dStack-owned formula files before operating. Formula synchronization does not modify historical
feature graphs.

Stable configuration lives in Git and Beads. dStack has no database, scheduler, setup ledger, migration state, or
ownership cache.

## Daily use and concurrency

Use the [command contracts](../reference/cli.md) to plan, authorize, implement, reconcile, and deliver work. Beads is
the sole authority for readiness, dependencies, gates, claims, and completion. Git is the sole authority for content,
worktrees, commits, and delivery history.

If a normal feature command detects an older formula contract on approved active work, the controller requests an
internal semantic audit. A no-change audit is cached by updating the audited formula version; a material plan delta is
shown to the user and requires renewed approval. This is review of current intent, not migration of historical Beads.

Each feature or alignment uses a conventional native Git worktree. Native Beads claims arbitrate concurrent workers.
Clean completed worktrees with native Git after delivery and after confirming no uncommitted files remain.

## Upgrade and uninstall

Upgrades replace dStack-owned installed formulas automatically. Existing approved work is audited only when a formula's
semantic contract version changes. No repository-wide migration is performed.

To uninstall, remove the Pi package through Pi's package mechanism. Repository-owned documentation, Beads history, and
Git history remain project data.
