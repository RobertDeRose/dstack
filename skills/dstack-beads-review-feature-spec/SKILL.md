---
name: dstack-beads-review-feature-spec
description: "Review, reconcile, commit, and approve the specification boundary of a poured dstack feature molecule."
---

# Review feature specification

Read the `dstack-beads-core` skill and every core reference before acting.

Use the user's input as an optional feature Bead ID, exact slug, or unique title
selector. This command owns the specification step and the feature's native
human approval gate. It does not implement feature tasks.

When the user supplies no feature selector, resolve the feature in this order:

1. use the exact feature root most recently resolved by `/start-feature` in the
   current Pi session;
2. otherwise, if the current Git worktree is on `feat/<slug>`, resolve the one
   current dstack feature whose root metadata/branch matches that branch;
3. otherwise, if the current worktree path exactly matches one current feature
   root's recorded worktree path, use that feature;
4. otherwise stop and show viable open feature roots instead of guessing.

An explicit selector always overrides the session default. Do not persist an
"active feature" label or custom state file.

## Resolve and verify

1. Run the setup doctor.
2. Resolve exactly one open feature root through Beads JSON using the
   selector/default rules above.
3. Resolve the specification step, implementation-approval milestone,
   implementation workstream, closeout step, and human gate through their native
   labels/relationships.
4. Locate the Beads-managed feature worktree and verify branch `feat/<slug>`.
5. Atomically claim the specification step. If another agent owns it, stop and
   report the owner instead of replacing the claim.
6. Read:
   - the feature design;
   - the dynamic implementation children;
   - task dependencies, acceptance criteria, and validation expectations;
   - relevant project plans, decisions, reader docs, source, tests, and history.

## Review

Perform an independent specification/readiness review against the current
repository. Check at least:

- goal and success criteria;
- scope and non-goals;
- architecture and interfaces;
- failure, security, compatibility, migration, and operational behavior;
- task decomposition and dependency correctness;
- testability and expected validation;
- documentation impact;
- unnecessary complexity and YAGNI concerns.

Use the shared review loop. Correct clear defects in the design and Beads graph.
Ask the user one targeted question at a time when accepted intent cannot be
resolved from repository evidence.

A task missing optional execution metadata does not block specification
approval when its intent and acceptance criteria are sufficient for serial work.
Closed historical tasks are irrelevant to this new molecule.

## Reconcile dynamic work

When adding or replacing implementation children, follow the core workflow
reference exactly: correct epic parent, labels, approval-milestone dependency,
acceptance criteria, and validation. The gate blocks the approval milestone; do
not attach a gate ID directly to a dynamic task. Use native dependencies for real
ordering. Do not create reviewer/coordinator tasks.

## Commit and approve

When the design and task graph are accepted:

1. commit the specification changes in the feature worktree;
2. capture the commit SHA;
3. run the verification review against that committed boundary;
4. correct findings and amend the private specification commit when safe;
5. record the final commit and review evidence in a Markdown Beads comment;
6. set the specification step's external reference to `git:<commit>`;
7. close the specification step;
8. resolve the unique human gate blocking the implementation-approval milestone;
9. claim the now-ready approval milestone, add a concise authorization comment,
   and close it;
10. verify the implementation children now participate in the native ready
    frontier according to their remaining dependencies.

Invocation of `/review-feature-spec` supplies the human authorization represented
by the gate once the interactive review has resolved all product decisions. Do
not ask for a redundant second approval merely to close that gate.

If the review remains blocked by unresolved intent, leave the specification step
open, the gate unresolved, and the approval milestone blocked. If an interruption
occurs after gate resolution but before milestone closure, resume the existing
milestone rather than creating another approval record.

Update the roadmap entry to `in-progress` only after the gate is resolved and
the approval milestone is closed.

## Return

- feature, worktree, and design boundary;
- specification review findings and corrections;
- user decisions;
- implementation graph changes;
- committed specification SHA;
- review/verification outcomes;
- specification close result, gate resolution, and approval-milestone closure;
- native ready and blocked work;
- exact next `/implement-feature` command; when continuing the same Pi
  session, show `/implement-feature` without a redundant feature selector.
