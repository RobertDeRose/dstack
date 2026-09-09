---
dstack-managed: true
name: dstack-close-feature
description: "Review delivered intent, return defects, publish feature documentation, and close the feature."
disable-model-invocation: true
---

# Close feature

The public lifecycle calls the final Beads step the **close step**. Its stable internal ID/label role remains `audit` /
`dstack:step:audit` for compatibility.

## dStack operations

Use these dStack commands in this stage:

```bash
dstack worktree --bead <feature-or-descendant>
dstack check feature --bead <root> --include-plan
dstack docs export-design --bead <root> --scaffold
dstack check docs --slug <slug>
dstack docs commit --bead <root>
dstack check feature --bead <root> --include-plan --require-docs
```

Enter the returned feature worktree before writing documentation. The first feature check collects deterministic
evidence for semantic review. The final feature check runs after documentation is committed or confirmed unchanged.

## Review before claiming

Resolve workflow position with `bd mol current <root> --json` or focused status queries plus `bd mol progress` for a
large graph. Read the close step with comments and inspect its ownership. Repeat semantic review when the close step is
already in progress. Do not claim it merely because Beads reports it ready.

If the close step is already closed, do not rewrite delivered history or repeat publication/claim operations. Run
project validation and the final dStack feature check, then complete only omitted implementation-epic/root closure if
those checks pass. Report failures rather than reopening delivered work.

Before the first feature check, inspect every implementation child and ensure the close step directly depends on it with
a `blocks` edge. Add any missing edge with `bd dep add <close> <task> --type blocks`; this repairs an older molecule or
an interrupted task-creation sequence without creating replacement workflow state.

Run `dstack check feature --bead <root> --include-plan`. Read the approved plan and relevant accepted decisions before
comparing intent with code. Use focused `bd show`, `bd history`, and `git show` reads when additional detail is needed
instead of recollecting the entire feature check. Follow `next_offset` when a summary is paged. Compare intent,
decisions, tasks, canonical commits, tests, code, and current documentation. Run the repository's documented validation
contract. Feature-check output is evidence, not semantic approval.

Do not write feature documentation until this review passes.

## Return findings

For a clear defect owned by an implementation task, read existing comments, record the evidence and acceptance gap once,
ensure the close step still directly depends on that task, reopen and unassign the task so Beads can make it ready,
release an in-progress close step through Beads status/assignee fields if necessary, and return `/implement <root>`.

For an unowned finding, create one bounded implementation child with `dstack:work:implementation`, planned scope in
`description`, accepted approach in `design`, observable `acceptance_criteria`, the direct approval blocker, and a
`discovered-from` link to the close step. Immediately run `bd dep add <close> <task> --type blocks`; if interrupted
after creation, repair that missing edge on resume before trusting close readiness. Leave execution notes empty and
create at most one correction for each finding.

For material ambiguity, comment with the contradiction, create a Beads human gate that directly blocks the close step
without secondary parentage, and ask one focused question. Record the accepted decision after the answer. If it changes
approved intent, update the plan and affected task, reopen/unassign that task, resolve only the ambiguity gate, and
return `/implement <root>`. If no task owns the affected outcome, create the bounded correction above before resolving
the gate.

## Publish and close

After semantic review passes and every implementation task is closed, resume or claim the open ready close step. Then:

1. Run `dstack docs export-design --bead <root> --scaffold`. It fills only unambiguous missing documentation structure;
   repair reported duplicate headings or misplaced includes explicitly.
2. Fill or update the feature index title, `Overview`, and `User Impact`. Keep the single exported design include under
   `Implemented Design`; do not rewrite or duplicate the exported design.
3. Run `dstack check docs --slug <slug>` and the repository's documentation validation.
4. Stage only the feature documentation and its `SUMMARY.md` entry, then run `dstack docs commit --bead <root>`. Accept
   an unchanged result when valid documentation is inherited from the base; do not create an empty replacement commit.
5. Run `dstack check feature --bead <root> --include-plan --require-docs`.

Propose reusable memory additions or corrections with exact content when close yields durable guidance.

After all checks pass, close the implementation epic, close step, and feature root, skipping already-closed issues on
resume. Do not use a project-wide epic cleanup sweep. Verify their Beads statuses. Report validations, decisions,
corrections, documentation result, and workflow status. Merge or push only when separately authorized.
