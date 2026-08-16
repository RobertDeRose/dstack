---
name: dstack-beads-start-feature
description: "Pour the native dstack feature molecule, create its worktree and design, and add dynamically gated implementation work."
---

# Start feature

Read the `dstack-beads-core` skill and every core reference before acting.

Use the user's input as the feature selector, goal, constraints, non-goals, and
optional base branch. Default the base branch to `dev` only when that branch
exists and the user did not provide another target.

## Preconditions

1. Run the setup doctor.
2. Read `docs/src/planned-features.md` when present.
3. Resolve a stable kebab-case slug. Do not guess major product intent.
4. Search existing feature molecule roots before pouring another. Reuse the
   exact existing open molecule or stop on ambiguity.
5. Verify the intended base branch and capture its commit.

## Native worktree

Use Beads' native worktree commands and the core worktree reference.

- Branch: `feat/<slug>`.
- Create the branch from the intended base commit when it does not exist.
- Create or reuse one Beads-managed worktree.
- Verify its Git root and branch before writing.
- Never write the design in the caller's worktree and copy it afterward.

## Pour the feature molecule

From the repository with the shared Beads database, run the persistent proto:

```bash
bd mol pour dstack-feature \
  --var feature_title="<title>" \
  --var feature_slug="<slug>" \
  --var base_branch="<base-branch>" \
  --var design_path="docs/src/features/<slug>/design.md" \
  --json
```

Capture the returned molecule root ID. Update the root using native Beads fields:

- title `Feature: <title>`;
- labels `workflow:feature` and `feature:<slug>`;
- external reference `git:<base-commit>`;
- metadata containing the slug, base branch, branch, design path, and worktree
  path.

Resolve exactly one specification step, implementation-approval milestone,
implementation workstream, closeout step, and open human gate using the core
Beads workflow reference.

## Design

Create or update only:

```text
docs/src/features/<slug>/design.md
```

Do not create `tasks.md`.

The design must state the goal, accepted requirements, non-goals, architecture,
interfaces and data flow, failure behavior, security and compatibility
boundaries, rollout or migration concerns, documentation impact, validation,
and unresolved decisions.

Include a small workflow section listing the feature molecule ID and telling
agents to inspect live work through `bd mol show` or `bd mol progress` rather
than duplicating task details in Markdown.

## Dynamic implementation work

Create bounded children beneath the implementation epic. Every child must:

- use `--no-inherit-labels`;
- carry `dstack:work:implementation` and `feature:<slug>`;
- depend on the implementation-approval milestone;
- contain context, acceptance criteria, and expected validation.

Do not pass the human gate ID through `--waits-for-gate`; that flag controls
`all-children`/`any-children` fan-in for a separate `--waits-for` relationship.
The formula gate blocks the task-sized approval milestone, and implementation
children become ready when that milestone closes.

Model genuine implementation dependencies with native Beads edges. Leave
independent children unordered.

The human gate stays open and the approval milestone remains blocked.
`/start-feature` does not authorize implementation.

## Planning reconciliation

Update the roadmap entry to `in-spec`. Complete any `dstack:feature-idea` TODO
that this molecule replaces and comment with the molecule ID.

## Commit behavior

Do not create a commit automatically. Offer exactly two next actions:

1. `/review-feature-spec <slug>`;
2. create one draft-spec commit in the feature worktree.

A draft commit does not close the specification step or resolve the gate.

## Return

- feature root, stable steps, approval milestone, and human gate IDs;
- base branch/commit, feature branch, and verified worktree path;
- design path;
- dynamic implementation tasks and dependency summary;
- native molecule progress;
- unresolved decisions;
- roadmap/TODO reconciliation;
- the two allowed next actions.
