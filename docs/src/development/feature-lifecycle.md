# Feature lifecycle

dStack is opt-in. A feature moves through planning, review and approval, implementation, and close. `/audit-project` is
a separate repository-wide operation that may create a remediation feature when it finds actionable drift.

```text
plan -> review -> human approval -> implementation tasks -> close
```

The implementation step is a Beads epic containing the feature's implementation tasks. Each task is blocked by approval
and remains a persistent blocker of the close step, so reopening a task blocks close again without rebuilding workflow
state.

## Planning

`/plan-feature` records the original request, observable outcomes, material questions and answers, and a publishable
design. Planning focuses on user intent rather than broad repository investigation.

Before new feature work is created, `dstack init` and `dstack check formula` must confirm that repository policy matches
the installed dStack package. Before the plan step closes, `dstack check plan --bead <feature>` validates the plan's
Beads fields and six required design sections:

- Goals
- User-facing behavior
- Implemented design
- Compatibility and constraints
- Validation
- Non-goals

The check validates structure, not whether an unresolved product decision remains. The workflow asks the user about those
semantic choices.

## Review and approval

`/review-plan` reconciles the plan with relevant current source, tests, documentation, accepted decisions, and focused
memory. It creates bounded implementation tasks with planned scope in `description`, accepted approach and invariants in
`design`, and observable outcomes in `acceptance_criteria`.

`dstack check review --bead <feature>` verifies the reviewed task graph before approval. Review never grants approval;
the user must explicitly approve the proposed scope before implementation tasks become ready.

## Implementation

`/implement` resumes implementation work already owned by the current agent before claiming another ready task. It enters
the registered feature worktree and reads the selected task's accepted fields, notes, comments, decisions, and blockers
as needed.

Task notes record delivered outcomes as ordered `Implementation:` fragments. Repository-changing tasks own one canonical
Git commit with exactly one `Task:` trailer. An intentional `No repository change:` task owns no canonical commit.

The target repository's own validation runs before the task is closed. `dstack commit --bead <task>` creates or corrects
the canonical unpublished task commit, and `dstack check task --bead <task>` validates task structure, Git evidence, and
worktree cleanliness. Implementation keeps current documentation aligned with behavior but leaves
`docs/src/features/<slug>/` to close.

## Close

`/close-feature` reviews the delivered repository against the approved plan before claiming the close step. It begins
with:

```text
dstack check feature --bead <feature> --include-plan
```

The skill reads accepted decisions and focused Beads/Git detail as needed, then compares intent, tasks, commits, tests,
code, current documentation, and the repository's own validation result. Clear defects return to their implementation
task. Unowned findings become a bounded correction task. Material ambiguity becomes a human gate that directly blocks
close.

Only after semantic review passes does close write feature documentation. The workflow exports the accepted design,
updates the feature index, runs structural and repository documentation validation, and calls
`dstack docs commit --bead <feature>`. Valid documentation inherited unchanged from the base needs no new or empty
commit.

The final deterministic check is:

```text
dstack check feature --bead <feature> --include-plan --require-docs
```

After all checks pass, close completes the implementation epic, close step, and feature root, skipping issues that are
already closed on resume.
