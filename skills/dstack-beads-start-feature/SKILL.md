---
name: dstack-beads-start-feature
description: "Resolve or initialize a feature, decide its design and task graph, and leave specification approval open."
---

# Start feature

Use the input as an exact Bead ID, slug, or title. New input becomes the feature
title. Default the base branch to `dev` when it exists, otherwise `main`, unless
the user specified one.

## Mechanics

Run:

```bash
python3 "{baseDir}/../dstack-beads-core/scripts/dstackctl.py" \
  feature initialize "<selector-or-title>" --base-branch <base>
```

The command resolves an existing current feature, refuses a closed/legacy
feature, or transactionally pours one molecule and creates/reuses its worktree.
Treat the returned root as the conversational active feature.

## Agent decisions

In the returned worktree, write or reconcile only the durable design. Decide:

- requirements and non-goals;
- architecture, interfaces, data flow, and failure behavior;
- security/compatibility/migration boundaries;
- documentation and validation impact;
- bounded implementation tasks and real dependencies.

Create each chosen task mechanically with `dstackctl feature add-task`.
Do not create `tasks.md`, workflow status docs, a commit solely for starting,
or reviewer/coordinator tasks.

Leave the specification step and human gate open. Return the design path, task
graph, unresolved decisions, and `/review-feature-spec` as the next command.
