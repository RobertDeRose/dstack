# Command contracts

Public slash commands are decision-oriented Pi prompt aliases. The bundled controller performs stateless deterministic
mechanics and emits JSON.

| Command | Reads | Authorized mutation | Successful boundary |
| --- | --- | --- | --- |
| `/setup-project [--force]` | Git, filesystem, Beads, tools | Reviewed setup plan only | Formula/docs policy validates; doctor reports healthy |
| `/plan-feature ...` | Repository and planned Beads work | Planned intent in Beads | One lossless planned feature |
| `/adopt-feature ...` | Legacy and current graph | Narrow explicit compatibility transition | One current native feature |
| `/review-feature-spec ...` | Design, graph, worktree | Materialization, graph reconciliation, human authorization | Committed design digest and native approval agree |
| `/implement-feature ...` | Native ready work and Git | Exact claim, repository change, evidence-backed close | Requested task closes or no ready task remains |
| `/close-feature ...` | Full candidate and delivery authority | Closeout, optional PR/direct delivery | Reviewed candidate or delivered root |
| `/project-alignment-review ...` | Current repository | Alignment analysis and correction plan | Human gate remains for explicit execution |
| `/project-alignment-execute ...` | Native ready corrections | Exact claim and evidence-backed close | Requested correction closes or none is ready |
| `/project-alignment-land ...` | Full correction candidate | Landing and optional delivery | Reviewed candidate or delivered root |
| `dstackctl audit feature ... --format json\|markdown` | Live Beads, reachable target Git history, optional worktree, mdBook, evidence, and delivery observations | None | Deterministic explicit audit facts; delivered evidence survives branch cleanup and nothing is published |

Internal controller leaves include `feature reauthorize` and `alignment
reauthorize` before approved graph changes, `delivery replace-pr` for an
explicit conflicting-gate repair, and `delivery cancel-pr-gate` for an explicit
switch from a unique PR blocker to direct delivery. These commands require
reasons and preserve native history; gate cancellation does not change the
GitHub pull request. Normal commands never invoke legacy repair.

## Retry and errors

Inspection, planning, and converged no-op commands are retry-safe. A task claim
is accepted only when the native atomic ready claim returns the exact expected
item; re-claiming lets Beads verify ownership. Closed exact work remains
idempotent. Completion requires a fully clean worktree and either reachable Git
footer evidence or `--no-repository-change` with a specific reason and no footer.

Errors are JSON on standard error and do not imply rollback. Validation errors
mean no intended terminal mutation occurred; conflict errors require fresh
native state; timeout and partial-recovery errors require inspection before
retry. Post-delivery finalization errors explicitly report completed delivery,
previous/delivered/observed target heads, root status, the finalization error,
and mutation uncertainty. See [recovery](../operations/recovery.md).
