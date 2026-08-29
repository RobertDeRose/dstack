# Command contracts

Public slash commands are decision-oriented Pi prompt aliases installed by `dstack install_skills`. The installed
`dstack ctl` controller performs stateless deterministic mechanics and emits JSON.

| Command | Reads | Authorized mutation | Successful boundary |
| --- | --- | --- | --- |
| `dstack install_skills` | Packaged Pi resources and existing global Pi guidance | dStack-owned skills/prompts and one managed `APPEND_SYSTEM.md` block | Installed Pi resources match the installed dStack version |
| `/plan-feature ...` | Repository and planned Beads work | Planned intent in Beads | One lossless planned feature |
| `/adopt-feature ...` | Legacy and current graph | Narrow explicit compatibility transition | One current native feature |
| `/review-feature-spec ...` | Design, graph, worktree | Materialization, graph reconciliation, human authorization | Committed design digest and native approval agree |
| `/implement-feature ...` | Native ready work and Git | Exact claim, repository change, evidence-backed close | Requested task closes or no ready task remains |
| `/close-feature ...` | Full candidate and delivery authority | Closeout, optional PR/direct delivery | Reviewed candidate or delivered root |
| `/project-alignment-review ...` | Current repository | Alignment analysis and correction plan | Human gate remains for explicit execution |
| `/project-alignment-execute ...` | Native ready corrections | Exact claim and evidence-backed close | Requested correction closes or none is ready |
| `/project-alignment-land ...` | Full correction candidate | Landing and optional delivery | Reviewed candidate or delivered root |
| `dstack ctl audit feature ... --format json\|markdown` | Live Beads, reachable target Git history, optional worktree, mdBook, evidence, and delivery observations | None | Deterministic facts include current terminal evidence, source revisions, limitations, and reconciliation; delivered evidence survives cleanup |

Adoption planning writes no durable state. Run `dstack ctl adopt plan LEGACY --classification-file CLASSIFICATION.json`
with a temporary strict `dstack.adoption-classification/v1` document; the command only reads Beads/Git and emits a
deterministic in-memory transformation plan. Apply the same file with
`dstack ctl adopt apply LEGACY --classification-file CLASSIFICATION.json`; all validation and complete graph planning
occur before pour or any other Beads mutation. Apply rereads every legacy, lifecycle, and affected external endpoint;
creates or reuses exact replacements from native parentage, labels, content, and supersession/association evidence; and
adds and verifies each compatible blocker before removing its legacy edge. Incoming external dependents are redirected
in add-before-remove order or the apply fails closed. Planned nonblocking context is preserved. Native readiness is
reread around each translation so an unrelated external task cannot become ready early. An incorporated decision keeps
the legacy root reachable until an approved committed-design retry resolves it; only then may old work and the root be
superseded. No migration map is stored.

`delivery inspect` is lifecycle-aware. An open root with closed terminal work is inspected from the active
target-to-candidate range and requires a clean registered candidate whose final terminal footer remains reachable. A
closed delivered root is inspected from the configured target and does not require the candidate branch or worktree.
Feature derivation uses the latest reachable closeout footer. Alignment derivation uses the latest reachable landing
footer, the latest correction footer when landing made no repository commit, or no candidate revision when no repository
change occurred. Sequential fixups and rebases are supported when footers remain reachable; the reported evidence source
comes from current reachable Git history.

Alignment review writes one temporary strict `dstack.alignment-plan/v2` JSON object and finalizes it with
`alignment finish-plan AUDIT --plan-file PLAN.json`. The object contains reviewed findings, correction content and
graph, validation expectations, documentation impact, deferred findings, and accepted risks. It stores no Git revision
or repository snapshot. Existing v1 Beads descriptions remain readable for historical inspection only; new plans use v2.
Markdown scaffolds and `finish-plan --summary-file` are not alignment-plan interfaces; Markdown reconciliation remains a
separate landing record.

Before Beads-backed controller commands, dStack validates the supported Beads binary and uses packaged formula source.
Approved active features whose `dstack.formula_version` is missing/stale return an internal `audit_required`
instruction; the installed dStack system guidance routes the semantic review automatically. `feature audit-complete` is
an internal transition used only when that review finds no material delta. Formula drift never triggers historical graph
normalization.

Internal controller leaves include `feature reauthorize` and `alignment reauthorize` before approved graph changes,
`delivery replace-pr` for an explicit conflicting-gate repair, and `delivery cancel-pr-gate` for an explicit switch from
a unique PR blocker to direct delivery. These commands require reasons and preserve native history. Gate cancellation is
Beads-only: it does not inspect candidate branches/worktrees, docs, footer evidence, or change the GitHub pull request,
and proves local Git HEAD/status are unchanged. Full candidate validation remains required for registration,
replacement, merge, and finalization. Normal commands never normalize historical workflow topology merely because a
formula changed.

## Retry and errors

Inspection, planning, and converged no-op commands are retry-safe. A task claim without a selector delegates selection
directly to Beads' atomic ready claim; dStack does not preselect a stale ready-list entry. An explicit `--task` remains
exact: the requested task must be ready, and any different native claim is verified-released (or ownership uncertainty
is reported). Closed exact work remains idempotent. Completion requires a fully clean worktree and either reachable Git
footer evidence or `--no-repository-change` with a specific reason and no footer.

Errors are JSON on standard error and do not imply rollback. Validation errors mean no intended terminal mutation
occurred; conflict errors require fresh native state; timeout and partial-recovery errors require inspection before
retry. Delivery validation derives the current candidate tip, requires clean worktrees and target ancestry, and checks
that the final terminal footer remains reachable; post-terminal commits must retain that footer. Direct fast-forward
delivery and PR ancestry that preserves the candidate are supported, including linear squash/rebase and sequential
fixups. Repeated footers in one commit, missing evidence, and unsupported nonlinear history fail without fallback.
Post-delivery finalization errors explicitly report completed delivery, previous/delivered/observed target heads, root
status, the finalization error, and mutation uncertainty. See [recovery](../operations/recovery.md).
