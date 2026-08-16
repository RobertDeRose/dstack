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

1. Compare the roadmap, existing feature designs, and poured feature molecules.
2. Report mismatches without changing live workflow state merely to make the
   views agree.
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

When a TODO is incorporated into the roadmap or started as a feature, mark it
done and comment with the resulting roadmap entry or feature molecule ID. Do
not keep the TODO and roadmap entry as competing status authorities.

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

- Status: planned | in-spec | in-progress | completed | deferred
- Overview:
- Requirements:
- Constraints:
- Non-goals:
- Success criteria:
- Risks and tradeoffs:
- Dependencies:
- Suggested validation:
- Next command: `/start-feature <feature-slug>`
```

Executable status comes from Beads. The roadmap status is a human planning view
and must be reconciled when a feature actually starts or delivers.

## Return

- roadmap status and changes;
- feature molecules and designs found;
- feature-idea TODOs retained, promoted, or completed;
- incomplete and deferred features;
- challenged assumptions;
- unresolved decisions;
- recommended next feature and exact `/start-feature` command.
