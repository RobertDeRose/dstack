# Delivery authority

Delivery is an explicit reconciliation boundary, not a side effect of finishing
implementation work. The candidate must have complete fan-in, approved design
content, reviewed documentation, required validation, clean worktrees, and
reachable `Beads:` footer evidence.

## Direct merge

Direct delivery is a clean fast-forward-only update of the target. dStack rechecks the candidate and target immediately
before mutation, uses a temporary native target worktree when the target is not checked out, verifies the delivered
head, and then finalizes Beads without changing delivered Git state.

A non-fast-forward target, dirty worktree, changed ref, missing evidence, active PR gate, or failed finalization stops
delivery. Open and closed unsuperseded PR gates remain active while they block the root; direct merge never cancels one
implicitly. Externally supplied branch/revision values must pass native Git validation before mutation; candidate
worktrees must use the conventional path, be attached to the expected branch, contain the target, and satisfy remote
assumptions. Internally created branches/worktrees are removed when post-creation verification fails, while cleanup
failures retain the primary diagnostic. dStack does not reset or rewrite history to make delivery pass.

## Pull request

PR delivery requires an `origin` remote containing the synchronized target and candidate refs. For a GitHub origin, `gh`
must be authenticated with permission to read the repository, push the candidate, create pull requests, and inspect
merge state. The user approves the aggregate title and body before creation.

Exactly one matching native PR gate may represent the delivery. Repeating
registration for that gate is safe. Missing, conflicting, or duplicate gates
fail without replacement; explicit `delivery replace-pr` repair requires a
reason and preserves native supersession history. Switching to direct delivery
requires `delivery cancel-pr-gate <selector> --reason <reason>`. Cancellation
closes an open gate, replaces its blocking dependency with a native nonblocking
relation, and verifies the graph before merge. It does not close or otherwise
change the GitHub pull request.

## Retry and finalization

Read-only preflight and matching registration are retry-safe. Retry only after observing current Git, Beads, remote, and
GitHub state; never assume a timed-out mutation failed. If a PR already exists, inspect it before registering or
replacing a gate.

Finalization snapshots candidate and target heads plus full worktree status. If root closure fails after delivery,
dStack reports `delivery_completed`, the previous, delivered, and observed target heads, observed root status, the
finalization error, and whether mutation is uncertain. If Beads finalization changes Git, it reports the same stable
facts plus changed paths, reopens the root when safe, and leaves delivered history untouched. Any rollback, reset,
revert, or PR correction is a separately authorized native Git or GitHub operation. See [recovery](recovery.md).
