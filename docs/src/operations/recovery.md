# Recovery and troubleshooting

Recovery starts from observed Beads and Git state. dStack never uses a shadow transaction ledger and never claims
rollback when an external mutation is uncertain.

## Setup failures

Setup planning is read-only. A changed digest means repository authority changed and the previous plan must not be
applied. For forced setup, apply consumes the saved plan in a detached worktree, targets the contained Beads database
explicitly, and preserves the native backup and worktree for inspection. Successful migrations retain those artifacts
until explicit verification and cleanup.

If forced setup times out, is interrupted, or reports uncertain mutation, stop. Preserve the plan, native backup, and
registered worktree, then use the controller's verification or rollback boundary. Do not use ad-hoc commands such as
`bd update` or `bd close`, label changes, manual Git repair, or documentation edits to reconstruct state. If native
rollback cannot prove the original Beads and Git state, leave all artifacts intact and report recovery required. A
pre-existing partial migration without a matching native backup is not automatically repairable.

## Delivery failures

- Dirty candidate or target: preserve the files, decide whether to commit, relocate, or discard them, then rerun
  preflight.
- Changed target or candidate: fetch and inspect; rebase or supersede only with explicit authorization. Delivery
  preflight permits a clean linear rebase or fixup before delivery when final terminal footer evidence remains
  reachable.
- Missing, duplicate, or later-only closeout footer evidence: treat the candidate derivation as unresolved. Do not
  substitute uncommitted files; restore supported fast-forward/ancestor history or record the limitation for manual
  recovery.
- Timed-out push, PR, merge, or Beads mutation: query the native system before retrying.
- Active PR gate before direct merge: keep the target unchanged; either continue PR delivery or explicitly run
  `delivery cancel-pr-gate` with the reason for switching modes. Gate cancellation does not change the GitHub pull
  request.
- Post-delivery finalization failure: keep delivered Git history intact; inspect `delivery_completed`,
  `previous_target_head`, `delivered_target_head`, `observed_target_head`, `root_status`, `finalization_error`, and
  `mutation_uncertain`. Reread Beads before retry. Use a normal revert or a separately authorized correction only when
  product content is wrong.
- Temporary target-worktree cleanup failure: dStack retains the path and reports `retained_path`, `path_exists`,
  `registered`, `dirty`, `cleanup_error`, and `recovery_guidance`. Inspect the retained files and
  `git worktree list --porcelain` before manually removing the worktree. Never use broad `git worktree prune` or delete
  a path while registration or state is unknown.

## Backup and restore

Back up the Git repository and Beads/Dolt data using their native supported mechanisms. Verify both backups
independently and test restoration in an isolated clone before destructive maintenance. Git bundles protect Git history;
they do not replace Beads/Dolt backup. Beads backup does not replace pushed Git refs. Never copy live database or socket
files as an ad-hoc backup.

After restore, run `git fsck`, Beads native diagnostics, setup doctor, documentation validation, and the relevant
acceptance scenario. Confirm remotes and worktrees before allowing writes.

## Interaction audit data

`.beads/interactions.jsonl` is local audit data and must remain ignored and untracked. Retention follows the repository
operator's privacy policy. Restrict filesystem access, redact before approved sharing, and delete under that policy; do
not commit it as documentation or workflow history.

## Common diagnostics

| Diagnostic | Meaning | Safe response |
| --- | --- | --- |
| Unsupported tool version | Compatibility evidence does not cover this binary | Install the pinned version or implement and review an upgrade |
| Formula byte mismatch | Installed lifecycle differs from package authority | Review setup plan; use explicit forced apply if replacement is intended |
| Worktree anomaly | Native Git topology is missing, duplicate, dirty, or prunable | Inspect `git worktree list --porcelain`; repair with native Git |
| Tracked runtime path | Machine-local Beads state entered Git | Remove it from the index without deleting needed local data |
| Missing reconciliation | A delivered feature lacks its durable result record | Author and review the record; dStack does not invent it |
| Remote or GitHub failure | Delivery prerequisites are unavailable | Repair origin, credentials, or permissions and rerun read-only preflight |
