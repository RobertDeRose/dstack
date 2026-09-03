# Recovery and troubleshooting

Recovery uses native authorities rather than a dStack journal.

## Workflow state

Inspect Beads directly with commands supported by the configured backend:

```bash
bd where --json
bd status --json
bd ping --json
bd mol current <feature-root>
bd blocked --parent <feature-root> --json
bd history <bead> --json
```

Release or reclaim abandoned native claims with Beads. Resolve malformed task relationships in Beads. dStack does not
replay intended workflow mutations and does not use `bd doctor` as an embedded-workspace health contract.

## Worktrees

Inspect native worktree state:

```bash
bd worktree list --json
git worktree list --porcelain
```

`dstack ctl worktree ensure` treats the Beads worktree inventory as authoritative, then independently verifies Git path,
branch, ancestry, and repository identity. It reports retained partial state rather than recording a registry.

## Formula

The formula is a normal tracked file under `.beads/formulas/`. Beads must already be initialized directly:

```bash
bd init --quiet --non-interactive
```

If the installed formula differs from the packaged contract, review the diff and run:

```bash
dstack ctl formula install --update
dstack ctl formula check
```

There are no owner/original swap files or crash-recovery protocol. dStack never initializes Beads in stealth mode.

## Git evidence

Use:

```bash
dstack ctl evidence commits --bead <id> --ref <base>..<feature>
```

Evidence is reconstructed from reachable `Beads: <id>` footers. A rebase or amend needs no Beads metadata repair.
