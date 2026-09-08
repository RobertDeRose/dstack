---
dstack-managed: true
name: dstack-close-feature
description: "Review delivered intent, return defects, then publish documentation and close the native feature."
disable-model-invocation: true
---

# Close feature

Run only when explicitly invoked. The formula's final step retains internal ID `audit` and label `dstack:step:audit`;
this skill provides its public close behavior.

## dStack operations

Use these dStack commands in this stage:

```bash
dstack worktree --bead <feature-or-descendant>
dstack audit --bead <root> --include-plan
dstack docs export-design --bead <root> --scaffold
dstack check docs --slug <slug>
dstack docs commit --bead <root>
dstack audit --bead <root> --include-plan --require-docs
```

Enter the returned feature worktree before publication writes. A `recovery_required` result must be resolved through
native Git before review continues. The first audit collects evidence for semantic review; the final audit is required
after accepted publication is committed or confirmed unchanged.

## Review before claiming

Resolve native position with `bd mol current <root> --json` or focused status queries plus `bd mol progress` for a large
graph. Read the final step with comments and inspect its ownership. Resume this agent's in-progress final step without
claiming again, but repeat semantic review. Do not claim the final step merely because native readiness exposes it.

If the final step is already closed, do not rewrite delivered history or rerun publication/claim operations. Run project
validation and the final dStack audit, then complete only omitted implementation-epic/root closure if those checks pass.
Report failures rather than reopening delivered work.

Before the first audit, inspect every implementation child and ensure the final step directly depends on it with a
native `blocks` edge. Add any missing edge with `bd dep add <audit> <task> --type blocks`; this also repairs an older
molecule or an interrupted task-creation sequence without creating replacement workflow state.

Run `dstack audit --bead <root> --include-plan`. Read the approved plan and relevant accepted decisions before comparing
intent with code. Use focused `bd show`, `bd history`, and `git show` reads for additional detail rather than
recollecting the whole audit. Follow `next_offset` when a summary is paged. Compare intent, decisions, tasks, canonical
commits, tests, code, and current documentation; current documentation and accepted decisions outrank stale memory. Run
the repository's documented validation contract. Audit collection is evidence, not semantic approval.

Do not write feature publication until this review passes.

## Return findings

For a clear defect owned by an implementation task, read existing comments, record the evidence and acceptance gap once,
ensure the final step still directly depends on that task, reopen and unassign the task so native readiness can expose
it, release an in-progress final step through native status/assignee fields if necessary, and return
`/implement <root>`.

For an unowned finding, create one bounded implementation child with `dstack:work:implementation`, planned scope in
`description`, accepted approach in `design`, observable `acceptance_criteria`, the direct approval blocker, and a
`discovered-from` link to the close step. Immediately run `bd dep add <audit> <task> --type blocks`; if interrupted
after creation, repair that missing edge on resume before trusting final-step readiness. Leave execution notes empty and
create at most one correction for each finding.

For material ambiguity, comment with the contradiction, create a native human gate that directly blocks the close step
without secondary parentage, and ask one focused question. Record the accepted decision after the answer. If it changes
approved intent, update the plan and affected task, reopen/unassign that task, resolve only the ambiguity gate, and
return `/implement <root>`. If no task owns the affected outcome, create the bounded correction above before resolving
the gate.

## Publish and close

After semantic review passes and every implementation task is closed, resume or claim the open ready final step. Then:

1. Run `dstack docs export-design --bead <root> --scaffold`. It fills only unambiguous missing publication structure;
   repair reported duplicate headings or misplaced includes explicitly.
2. Fill or update the feature index title, `Overview`, and `User Impact`. Keep the single exported design include under
   `Implemented Design`; do not rewrite or duplicate the exported native design.
3. Run `dstack check docs --slug <slug>` and the repository's documentation validation.
4. Stage only the feature publication and its SUMMARY entry, then run `dstack docs commit --bead <root>`. Accept an
   unchanged result when valid publication is inherited from the base; do not create an empty replacement commit.
5. Run `dstack audit --bead <root> --include-plan --require-docs`.

If the docs commit reports native Git recovery, resolve it before another dStack mutation. Do not manually reproduce its
commit/correction mechanics.

Propose reusable memory additions or corrections with exact content and write them only after user approval.

After all checks pass, close the implementation epic, final step, and molecule root, skipping already-closed items on
resume. Do not use a project-wide epic cleanup sweep. Verify their native statuses; an empty ready queue does not prove
completion. Report validations, decisions, corrections, publication result, and native status. Merge or push only when
separately authorized.
