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

Resolve the feature, fixed steps, slug, and close-review gate with await ID `close-<slug>-review`. For active legacy
molecules without that gate, preserve their existing final-step behavior; do not migrate the graph.

While the fixed gate is open, collect bounded evidence with `dstack audit <root>`. Fetch full plan, task, decision, or
history details only for a material discrepancy. Run the target repository's documented project-validation contract.
Compare approved intent and decisions with implementation tasks, canonical commits, tests, current code, and current
documentation. Repository documentation and accepted decisions outrank stale memory.

Do not write feature documentation yet.

## Return findings

For a clear defect owned by an implementation task:

1. comment with the evidence and acceptance gap;
2. reopen that task and clear its assignee so native readiness can expose it; and
3. return `/implement <root>` without resolving the close-review gate.

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
2. Claim the now-ready `dstack:step:audit` step.
3. Run `dstack docs export-design --feature <root>`.
4. Write `docs/src/features/<slug>/index.md` with one title, meaningful `Overview` and `User Impact` sections, and an
   `Implemented Design` section containing exactly `{{#include design.md}}`. Add exactly one SUMMARY link to the index.
5. Run `dstack check docs --feature <slug>` and the repository's documentation validation.
6. Stage only that feature directory and SUMMARY entry, then run `dstack docs commit --feature <root>`. The generated
   commit is `docs(<slug>): <feature title>`, has no body, and carries one final-step `Task:` trailer.
7. Run `dstack audit <root> --require-docs`.

If one unpublished close-owned commit already exists but its stored feature title is stale, rerun the docs commit
command from a clean worktree to reword it. Never rewrite ambiguous or published close evidence.

Propose reusable memory additions or stale-memory corrections to the user with exact keys and content. Run `bd remember`
only after explicit approval; memory is never completion evidence.

Close the final step and molecule root only after all checks pass. Report validations, decisions, corrections, final
commit, and native status.
