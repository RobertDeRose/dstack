# Operations

This section is the operator contract for installing and running dStack. The
[compatibility reference](../reference/compatibility.md) lists supported runtime behavior.

## Install and configure

Install dStack as a normal Python tool from a checkout:

```bash
uv tool install --python 3.14 /path/to/dstack
```

The first dStack command to run is:

```bash
dstack install_skills
```

Use a non-default Pi agent directory with either supported form:

```bash
dstack install_skills --agent-dir /path/to/pi-agent
PI_CODING_AGENT_DIR=/path/to/pi-agent dstack install_skills
```

This installs/updates the dStack decision skills under `~/.pi/agent/skills/`, slash-command prompts under
`~/.pi/agent/prompts/`, and a compact managed dStack block in `~/.pi/agent/APPEND_SYSTEM.md`. Reload Pi after
installation or upgrade. The `dstack-beads-core` skill is intentionally not installed; its stable cross-workflow
guardrails are part of the system-prompt additive.

The normal controller entry point is `dstack ctl ...`. It uses the repository from which it is invoked unless `--root`
is supplied explicitly, initializes Beads when needed, and uses packaged dStack formulas as authority before operating.
There is no setup workflow and no formula migration.

Required external tools are `uv`, Beads 1.2.2 exactly, and mdBook 0.5.3 exactly when documentation validation is
required. The installed controller validates the same mdBook version exercised by repository tooling and CI. The dStack
repository's `mise.toml` remains contributor/CI tooling, not the installed CLI launcher.

Stable configuration lives in Git and Beads. dStack has no database, scheduler, setup ledger, migration state, or
ownership cache.

## Daily use and concurrency

Use the [command contracts](../reference/cli.md) to plan, authorize, implement, reconcile, and deliver work. Beads is
the sole authority for readiness, dependencies, gates, claims, and completion. Git is the sole authority for content,
worktrees, commits, and delivery history.

Formula-version drift never changes the native ready set for approved active work. When that feature is explicitly
reviewed under the current formula contract, the feature-review skill compares the existing approved intent with the
current semantic contract without changing topology. A no-change audit updates only the root formula version; a material
plan delta is shown to the user and requires renewed approval through the existing specification/approval boundary. This
is review of current intent, not migration or normalization of historical Beads.

Each feature uses a conventional native Git worktree. Native Beads claims arbitrate concurrent workers.
Clean completed worktrees with native Git after delivery and after confirming no uncommitted files remain.

## Upgrade and uninstall

Upgrade by reinstalling from the same checkout or source, then refresh Pi resources:

```bash
uv tool install --force --python 3.14 /path/to/dstack
dstack install_skills
```

Formula contract changes audit active approved work only when needed. Existing historical work is never repository-wide
migrated to a newer formula shape. `/project-audit` is read-only and proposes ordinary feature work when current code
and documentation diverge.

To uninstall, remove the uv tool and delete the dStack-owned skills/prompts and managed APPEND_SYSTEM block if desired.
Repository-owned documentation, Beads history, and Git history remain project data.
