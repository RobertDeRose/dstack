# Command contracts

Public slash commands are decision-oriented Pi prompt aliases installed by `dstack install_skills`. The installed
`dstack ctl` controller performs stateless deterministic mechanics and emits JSON.

| Command | Reads | Authorized mutation | Successful boundary |
| --- | --- | --- | --- |
| `dstack install_skills` | Packaged Pi resources and existing global Pi guidance | dStack-owned skills/prompts and one managed `APPEND_SYSTEM.md` block | Installed Pi resources match the installed dStack version |
| `/plan-feature ...` | Repository and planned Beads work | Planned intent in Beads | One lossless planned feature |
| `/review-feature-spec ...` | Design, graph, worktree | Materialization, graph reconciliation, human authorization | Committed design digest and native approval agree |
| `/implement-feature ...` | Native ready work and Git | Exact claim, repository change, evidence-backed close | Requested task closes or no ready task remains |
| `/close-feature ...` | Full candidate and delivery authority | Closeout, optional PR/direct delivery | Reviewed candidate or delivered root |
| `/project-alignment-review ...` | Current repository | Alignment review summary and native correction graph | Human gate remains for explicit execution |
| `/project-alignment-execute ...` | Native ready corrections | Exact claim and evidence-backed close | Requested correction closes or none is ready |
| `/project-alignment-land ...` | Full correction candidate | Landing and optional delivery | Reviewed candidate or delivered root |
| `dstack ctl audit feature ... [--verbose] --format json\|markdown` | Native feature Bead and Git/worktree facts; `--verbose` also reads full Beads/Git/docs evidence | None | Native identity/Git facts by default; complete audit facts only on request |

## Native authority

Beads owns workflow state, correction content, dependencies, gates, and readiness. Git owns repository content and
history. dStack does not use an external workflow packet, classification file, migration map, or shadow graph.

Default feature/alignment inspection and feature audit output return the native workflow root Bead plus deterministic
branch/worktree facts only. They do not project a next task, required evidence, blocker explanation, progress, or
delivery state. `bd ready` is the ready-work surface; dStack claim commands delegate the atomic claim to native
`bd ready --claim`. Use `feature inspect --verbose`, `alignment inspect --verbose`, or `audit feature --verbose` only
when complete diagnostic records are required.

Alignment review stores accepted corrections directly under the native correction workstream. A concise temporary
Markdown summary records findings, rejected or deferred findings, accepted risks, validation expectations, and
three-audience documentation impact without repeating complete correction definitions. Finish the review with:

```bash
dstack ctl alignment finish-plan AUDIT --summary-file /tmp/alignment-review.md
```

The controller derives the approval digest from that summary and the exact current correction Beads. Approval recomputes
the same authority, so a correction or dependency change after review is rejected.

Historical active graphs that do not contain the current molecule are not migrated by dStack. They remain native Beads
work until completed or retired there, or until the user explicitly plans a new current feature.

Before Beads-backed mutation commands, dStack validates the supported Beads binary and uses packaged formula source.
Formula-version drift does not override native Beads readiness for already approved work. When an approved feature is
explicitly reviewed under a newer or unknown contract, the feature-review skill judges the existing design/tasks
semantically without mutating the native graph. A no-change review records only the root contract version through
`feature audit-complete`; a material delta requires renewed user approval and the existing reauthorization/specification
boundary. Formula drift never creates work or normalizes historical graph shape.

## Delivery

`delivery inspect --fetch` fetches first when requested, then performs one inspection. An open root with closed terminal
work is inspected from the active target-to-candidate range and requires a clean registered candidate whose final
terminal footer remains reachable. A closed delivered root is inspected from the configured target and does not require
the candidate branch or worktree. Sequential fixups and rebases are supported when exact Beads footers remain reachable.

Internal controller leaves include `feature reauthorize` and `alignment reauthorize` before approved graph changes,
`delivery replace-pr` for an explicit conflicting-gate repair, and `delivery cancel-pr-gate` for an explicit switch from
a unique PR blocker to direct delivery. These commands require reasons and preserve native history. PR identifiers are
canonical positive integers. Gate cancellation is Beads-only: it does not inspect candidate branches/worktrees, docs,
footer evidence, or change the GitHub pull request. Full candidate validation remains required for registration,
replacement, merge, and finalization. Normal commands never normalize historical workflow topology merely because a
formula changed.

## Retry and errors

Read-only inspection and converged no-op commands are retry-safe and do not initialize an absent Beads workspace.
Planning commands that create planned Beads state, along with other mutation commands, initialize Beads when needed. A
task claim without a selector delegates selection directly to Beads' atomic ready claim; an explicit `--task` remains
exact.

Expected validation, filesystem, malformed-response, timeout, and conflict failures are JSON on standard error. A
timeout identifies the native command and reports captured output plus whether the operation may have mutated state. No
error implicitly claims rollback. See [recovery](../operations/recovery.md).
