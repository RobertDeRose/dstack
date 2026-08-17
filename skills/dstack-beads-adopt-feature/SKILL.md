---
name: dstack-beads-adopt-feature
description: "Adopt one active legacy dstack feature epic into the current formula-backed workflow without rewriting completed work or Git history."
---

# Adopt feature

Read the `dstack-beads-core` skill and every core reference before acting.

Use this command only for an **open feature that was already started under the
legacy dstack workflow**. It is a one-time compatibility path, not a general
migration engine.

Use the user's input as an explicit legacy root ID, exact feature slug, or
unique feature title.

## Safety boundary

This command authorizes Beads mutations required for adoption only. It does not
authorize source changes, Git commits, rebases, merges, pushes, PRs, branch or
worktree deletion, or implementation.

Never delete the legacy graph. Preserve it as closed historical evidence.

## 1. Resolve the legacy feature

1. Run the dstack setup doctor.
2. Resolve exactly one open legacy feature root.
3. Refuse a root that is already a current dstack molecule with the stable
   `dstack:step:*` children.
4. Read the complete legacy descendant graph, including closed descendants,
   comments, metadata, and dependencies. Ignore legacy commit-SHA mappings; they
   are not migrated into the current workflow.
5. Read the design path, base branch, and feature branch/worktree when present.
   Do not create a new feature branch or rewrite history.

## 2. Classify legacy descendants

Classify every open descendant into exactly one bucket:

- **remaining implementation work** — a concrete product/code outcome that is
  still required;
- **pending closeout validation** — validation or documentation reconciliation
  that belongs at feature close;
- **decision required** — unresolved product/architecture intent;
- **legacy workflow ceremony** — reviewer seats, reconciliation coordinators,
  delivery coordinators, finite-review machinery, or similar old-dstack state.

Completed legacy implementation tasks remain closed historical evidence. Do not
copy or reopen them.

## 3. Pour the current feature workflow

Pour `dstack-feature` with the existing feature identity:

```bash
bd mol pour dstack-feature \
  --var feature_title="<title>" \
  --var feature_slug="<slug>" \
  --var base_branch="<base-branch>" \
  --var design_path="<design-path>" \
  --json
```

Update the new root with concrete feature-level state only:

- title `Feature: <title>`;
- labels `workflow:feature` and `feature:<slug>`;
- metadata: `feature_slug`, `base_branch`, `design_path`, `adopted_from`, plus
  existing `branch` and `worktree_path` when known.

Do not carry legacy Git SHAs or external Git references into the new workflow.

Formula child steps intentionally contain only stable `dstack_step` identity.
Do not duplicate feature slug, branch, or design metadata onto stable children.

Resolve the unique specification step, approval milestone, implementation epic,
closeout step, and human gate from stable step labels and relationships.

## 4. Carry forward only real remaining work

For each still-valid legacy implementation task, create one replacement child
under the new implementation epic:

- use `--no-inherit-labels`;
- labels: `dstack:work:implementation` and `feature:<slug>`;
- depend on the new approval milestone;
- preserve the bounded outcome, acceptance criteria, and required validation;
- note completed prerequisite legacy tasks that must be reconciled rather than
  reimplemented.

Supersede the legacy implementation task with its replacement.

Do not recreate reviewer/coordinator tasks.

## 5. Preserve dependencies and closeout requirements

- Preserve meaningful **active external blockers** from the legacy feature root
  on the new root. Do not copy parent-child, supersedes, or dependencies on
  already closed historical workflow ceremony.
- Record pending validation/documentation requirements on the new closeout step
  in one concise Markdown comment. Do not recreate old validation or delivery
  coordinators.
- Record unresolved product/architecture decisions on the new specification
  step and leave them for `/review-feature-spec`.

## 6. Supersede legacy workflow state

After every open legacy descendant is classified:

- supersede old specification/reviewer/reconciliation ceremony with the new
  specification step;
- supersede the old implementation coordinator with the new implementation epic;
- supersede validation/documentation/delivery ceremony with the new closeout
  step;
- supersede the legacy feature root with the new root **last**.

Never supersede already closed historical implementation tasks merely to make
an old graph look tidy.

## 7. Adoption record and verification

Add one Markdown comment to the new root containing:

- legacy root;
- branch/worktree when known;
- completed legacy implementation work retained as history;
- legacy-to-new replacement mappings;
- obsolete ceremony superseded;
- pending closeout validation;
- unresolved decisions;
- external blockers preserved;
- statement that no source or Git history changed during adoption.

Then verify:

1. the legacy root is closed/superseded;
2. it has no open executable descendants;
3. the new human gate is open;
4. the new approval milestone is blocked;
5. implementation replacement tasks are blocked on approval;
6. the new specification task is the only feature task eligible to proceed;
7. the feature branch/worktree are unchanged;
8. no poured current-dstack child contains unresolved `{{...}}` metadata or
   labels.

Do not close the new specification step or resolve its gate during adoption.

## Return

Report only:

- new root and stable step/gate IDs;
- branch/worktree;
- completed work preserved;
- replacement implementation tasks;
- pending closeout validation and unresolved decisions;
- legacy-to-new supersession mapping;
- preserved external blockers;
- exact next command:

```text
/review-feature-spec <slug>
```
