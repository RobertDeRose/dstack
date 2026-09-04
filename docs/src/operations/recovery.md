# Recovery

Recover each authority from its native tool.

## Beads

```bash
bd where --json
bd status --json
bd ping --json
bd blocked --parent <feature-root> --json
bd history <bead> --json
```

Inspect and release claims, correct relationships, and resolve gates with native Beads commands.

## Worktrees

```bash
bd worktree list --json
git worktree list --porcelain
```

`dstack worktree --bead <feature-or-descendant>` verifies the registered worktree path, branch, repository, and ancestry
before returning success.

## dStack contract

The project formula and scoped Beads prime are installed as `.beads/formulas/dstack-feature.formula.toml` and
`.beads/PRIME.md`. Run `dstack init` only when the Beads workspace is missing. A failed native `bd where` with an
existing `.beads` path is treated as unhealthy and returned unchanged for deliberate recovery. For a healthy existing
workspace, use the lower-level commands:

```bash
# Missing workspace
dstack init

# Existing workspace
dstack install formula --update
dstack check formula
```

Review and commit the formula diff before using it for feature work. Do not delete, replace, or silently reinitialize an
ambiguous workspace; inspect the native Beads error and ask whether to recover or restart.

## Git evidence

`dstack check task --bead <task>` validates evidence from reachable `Beads: <task>` footers in Git history.
