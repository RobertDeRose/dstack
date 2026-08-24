# Recovery and troubleshooting

Recovery starts from observed Beads and Git state. dStack never uses a shadow transaction ledger and never claims
rollback when an external mutation is uncertain.

## Setup failures

Rerun setup plan first. A changed digest means the repository authority state changed and the previous plan must not be
applied. Apply restores setup-owned files and removes an internally created Beads directory when safe. For legacy moves
or Beads normalization that cannot be compensated, the error identifies the observed boundary: inspect the listed files
and native issues, correct them with native operations, then plan again.

## Delivery failures

- Dirty candidate or target: preserve the files, decide whether to commit,
  relocate, or discard them, then rerun preflight.
- Changed target or candidate: fetch and inspect; rebase or supersede only with
  explicit authorization.
- Timed-out push, PR, merge, or Beads mutation: query the native system before
  retrying.
- Post-delivery finalization failure: keep delivered Git history intact; inspect
  the reported heads and root state. Use a normal revert or a separately
  authorized correction when product content is wrong.

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
| Missing reconciliation | A delivered feature lacks its durable result record | Author and review the record; doctor does not invent it |
| Remote or GitHub failure | Delivery prerequisites are unavailable | Repair origin, credentials, or permissions and rerun read-only preflight |
