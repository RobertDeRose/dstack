---
dstack-managed: true
name: dstack-close-feature
description: "Review delivered intent, return defects, then publish documentation and close the native feature."
disable-model-invocation: true
---

# Close feature

Run only when explicitly invoked. The formula's final step retains internal ID `audit` and label `dstack:step:audit`,
but this skill provides its public close behavior.

## Review before claiming

Run `dstack worktree --bead <feature-or-descendant>` and enter the returned worktree before any publication writes.
Respect the single-writer boundary. A `recovery_required` result locates the interrupted worktree without repairing it.
Inspect `git status`; finish or deliberately abort the native Git operation and establish ownership of existing changes
before continuing. Do not claim work or write publication files during recovery.

Resolve native position with `bd mol current <root> --json` (or focused status queries plus `bd mol progress` for a
large graph). Read the final step with comments and inspect its ownership. Resume this agent's in-progress final step
without claiming again, but repeat the semantic review. A closed final step is not permission to rewrite delivered
history: skip publication and claims, run project validation and `dstack audit --bead <root> --include-plan --require-docs`,
and finish only omitted implementation-epic/root closure when those checks pass. Report failures rather than silently reopening delivered work.

Collect `dstack audit --bead <root> --include-plan`. Read the approved plan and relevant accepted decisions before
comparing intent with code; summaries alone cannot establish semantic compliance. Read selected tasks or decisions with
`bd show <id> --include-comments --json`, history with `bd history <id> --json`, and commit details with `git show <sha>`.
Do not recollect the whole audit merely to read one issue. Follow summary `next_offset` with `--offset` when necessary;
checks still cover all evidence. Rerun the complete audit after corrections and publication.
Run the repository's project validation. Compare intent, decisions, tasks, canonical commits, tests, code, and current
documentation. Documentation and accepted decisions outrank stale memory. Audit collection is not semantic approval.

Do not write feature documentation yet.

## Return findings

For a clear defect owned by an implementation task:

1. read existing task comments, then record the evidence and acceptance gap once;
2. reopen that task and clear its assignee so native readiness can expose it; and
3. return `/implement <root>`. If the final step was already in progress, release it through native
   status/assignee fields before returning work; its implementation fan-in remains authoritative.

When no task owns a finding, create one bounded implementation child with `dstack:work:implementation`, a planned
`description` (scope and non-goals), accepted `design` (approach and invariants), observable `acceptance_criteria`, a
direct approval blocker, and a `discovered-from` link to the close step. Leave execution notes empty until
implementation begins. Create at most one unowned correction per finding.

For material ambiguity, comment with the contradiction, create a native human gate that directly blocks the close step,
and ask one focused question. Do not add secondary parentage for discovery. After the answer, record an accepted
decision. If the answer changes approved intent, update the plan design and the owning task's acceptance criteria,
reopen and unassign that task, resolve only the ambiguity gate, and return `/implement <root>`. If no task owns the
affected outcome, create the bounded correction described above before resolving the ambiguity gate.

## Publish and close

After the complete review passes and every implementation task is closed:

1. Resolve the fixed close-review gate. For a legacy molecule without it, skip only this operation.
2. Resume this agent's in-progress final step or claim the open, now-ready `dstack:step:audit` step.
3. Run `dstack docs export-design --bead <root> --scaffold` from the feature worktree. This exports the native design
   verbatim and creates only missing index sections and the SUMMARY link. Existing prose is not overwritten.
4. Fill or update the index title, `Overview`, and `User Impact` from the accepted outcome. Keep the single native
   `{{#include design.md}}` under `Implemented Design`; do not rewrite the exported design or duplicate its prose.
4. Run `dstack check docs --slug <slug>` and the repository's documentation validation.
5. Stage only that feature directory and SUMMARY entry, then run `dstack docs commit --bead <root>`. The generated
   commit is `docs(<slug>): <feature title>`, has no body, and carries one final-step `Task:` trailer. If valid
   publication is inherited unchanged from the base, accept the no-op result; do not create an empty commit.
6. Run `dstack audit --bead <root> --include-plan --require-docs`.

If one unpublished close-owned commit already exists but its stored feature title is stale, rerun the docs commit
command from a clean worktree to reword it. Never rewrite ambiguous or published close evidence.

Propose reusable memory additions or stale-memory corrections to the user with exact keys and content. Run `bd remember`
only after explicit approval; memory is never completion evidence.

After all checks pass, close the implementation epic explicitly, then the final step, then the molecule root, skipping
already-closed items on resume. Do not use a project-wide epic cleanup sweep. Read their native statuses to verify
closure; an empty ready queue does not prove completion. Report validations, decisions, corrections, the final commit or unchanged inherited publication, and native status. Merge or push only when separately authorized.
