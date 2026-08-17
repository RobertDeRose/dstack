---
name: dstack-beads-plan-features
description: "Plan and prioritize project features while keeping executable workflow state out of the planning phase."
---

# Plan features

Read the `dstack-beads-core` skill and its discovery reference before acting.

Use the user's message as project or feature-planning input. This command plans;
it does not pour a molecule, create a feature branch/worktree, or implement.

## Sources

Read, when present:

- `docs/src/planned-features.md`;
- existing designs under `docs/src/features/`;
- open feature molecules in Beads;
- Beads TODOs labeled `dstack:feature-idea`;
- relevant project constraints and accepted decisions.

## Behavior

1. Compare planning documentation, existing feature designs, and current Beads
   work to understand product intent and dependencies.
2. Do not reconcile documentation to Beads lifecycle state. They have different
   responsibilities.
3. Ask targeted questions one at a time when product intent is genuinely
   unresolved.
4. Challenge scope, coupling, security, operability, and untestable requirements
   directly; propose a smaller or safer alternative.
5. Keep unresolved decisions explicit.
6. Update only `docs/src/planned-features.md` when a durable roadmap edit is
   warranted.
7. Do not create `tasks.md`.
8. Do not pour `dstack-feature` until `/start-feature` is invoked.

## TODO inbox

Use `bd todo add` only for lightweight ideas that are worth retaining but are
not ready for a full roadmap entry. Label them `dstack:feature-idea` with
`bd update` and add a short description when useful.

When a TODO becomes real planned work or a started feature, close or relate the
TODO using native Beads relationships. Do not copy workflow IDs into planning
documentation.

## Roadmap shape

Use this human-readable structure:

```markdown
# Planned Features

## Project Overview
## Goals
## Non-Goals
## Global Constraints
## Cross-Cutting Decisions
## Open Questions
## Feature Map

### `<feature-slug>`

- Overview:
- Requirements:
- Constraints:
- Non-goals:
- Success criteria:
- Risks and tradeoffs:
- Dependencies:
- Suggested validation:
```

Planning documentation describes what should exist and why. It does not carry
workflow status, Beads IDs, branch names, commit IDs, or next-command state.
Completed/implemented behavior belongs in durable feature/user/developer docs,
not in lifecycle bookkeeping fields.

## Return

- planning-document changes;
- feature molecules and designs found;
- feature-idea TODOs retained, promoted, or completed;
- incomplete and deferred features;
- challenged assumptions;
- unresolved decisions;
- recommended next feature and exact `/start-feature` command.
