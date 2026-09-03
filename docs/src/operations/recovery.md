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

`dstack ctl worktree ensure` verifies the registered worktree path, branch, repository, and ancestry before returning
success.

## dStack contract

The project formula and scoped Beads prime are installed as `.beads/formulas/dstack-feature.formula.toml` and
`.beads/PRIME.md`. Run `dstack init` when the Beads workspace is missing. For an existing workspace, use the lower-level
commands:

```bash
# Missing workspace
dstack init

# Existing workspace
dstack ctl formula install --update
dstack ctl formula check
```

Review the formula diff before using `--update`.

## Git evidence

```bash
dstack ctl evidence commits --bead <id> --ref <base>..<feature>
```

Evidence comes from reachable `Beads: <id>` footers in Git history.
