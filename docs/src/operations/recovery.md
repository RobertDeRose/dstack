# Recovery and troubleshooting

Recovery uses the native authorities rather than a dStack journal.

## Workflow state

Inspect Beads directly:

```bash
bd where --json
bd doctor --json
bd mol current <feature-root>
bd blocked --parent <feature-root> --json
bd history <bead> --json
```

Release or reclaim abandoned native claims with Beads. Resolve malformed task relationships in Beads. dStack does not
replay intended workflow mutations.

## Worktrees

Inspect native worktree state:

```bash
bd worktree list --json
git worktree list --porcelain
```

`dstack ctl worktree ensure` either verifies the exact conventional feature worktree or reports retained state for
manual inspection. It does not record a separate registry.

## Formula

The formula is a normal tracked file under `.beads/formulas/`. If the installed copy differs from the packaged contract,
review the diff and run:

```bash
dstack ctl infra install --update-formula
```

There are no owner/original swap files or crash-recovery protocol.

## Git evidence

Use:

```bash
dstack ctl evidence commits --bead <id> --ref <base>..<feature>
```

Evidence is reconstructed from reachable `Beads: <id>` footers. A rebase or amend needs no Beads metadata repair.
