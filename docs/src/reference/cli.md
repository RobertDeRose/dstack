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
| `dstackctl audit feature ... --format json\|markdown` | Live Beads, reachable target Git history, optional worktree, mdBook, evidence, and delivery observations | None | Deterministic facts include the immutable closeout candidate, source revisions, limitations, and reconciliation; delivered evidence survives cleanup |

Adoption planning writes no durable state. Run `dstackctl adopt plan LEGACY
--classification-file CLASSIFICATION.json` with a temporary strict
`dstack.adoption-classification/v1` document; the command only reads Beads/Git
and emits a deterministic in-memory transformation plan. Apply the same file
with `dstackctl adopt apply LEGACY --classification-file CLASSIFICATION.json`;
all validation and complete graph planning occur before pour or any other Beads
mutation.

Alignment review writes one temporary strict `dstack.alignment-plan/v1` JSON
object and finalizes it with `alignment finish-plan AUDIT --plan-file PLAN.json`.
The object includes the exact `baseline_commit`, correction content and graph,
validation expectations, documentation impact, deferred findings, and accepted
risks. Markdown scaffolds and `finish-plan --summary-file` are not alignment-plan
interfaces; Markdown reconciliation remains a separate landing record.

`setup.py doctor --delivery-mode merge|pr` requires an explicit delivery profile and reports the selected mode. Merge
checks only common/local requirements; PR adds a usable GitHub target remote, authenticated `gh`, and native Beads
`gh:pr` gate capability. No profile is inferred from incidental remote state.

Internal controller leaves include `feature reauthorize` and `alignment
reauthorize` before approved graph changes, `delivery replace-pr` for an
explicit conflicting-gate repair, and `delivery cancel-pr-gate` for an explicit
switch from a unique PR blocker to direct delivery. These commands require
reasons and preserve native history. Gate cancellation is Beads-only: it does
not inspect candidate branches/worktrees, docs, footer evidence, or change the
GitHub pull request, and proves local Git HEAD/status are unchanged. Full
candidate validation remains required for registration, replacement, merge, and
finalization. Normal commands never invoke legacy repair.

## Retry and errors

Inspection, planning, and converged no-op commands are retry-safe. A task claim without a selector delegates selection
directly to Beads' atomic ready claim; dStack does not preselect a stale ready-list entry. An explicit `--task` remains
exact: the requested task must be ready, and any different native claim is verified-released (or ownership uncertainty
is reported). Closed exact work remains idempotent. Completion requires a fully clean worktree and either reachable Git
footer evidence or `--no-repository-change` with a specific reason and no footer.

Errors are JSON on standard error and do not imply rollback. Validation errors mean no intended terminal mutation
occurred; conflict errors require fresh native state; timeout and partial-recovery errors require inspection before
retry. Delivery validation derives one closeout-footer candidate and requires clean candidate HEAD equality. Direct
fast-forward delivery and PR ancestry that preserves that candidate are supported; squash/rebase, duplicate or missing
footers, and unsupported nonlinear history fail without fallback. Post-delivery finalization errors explicitly report
completed delivery, previous/delivered/observed target heads, root status, the finalization error, and mutation
uncertainty. See [recovery](../operations/recovery.md).
