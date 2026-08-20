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
Treat the returned root as the conversational active feature. Pass that root
explicitly to later controller commands; omitted selectors are safe only from
its registered feature worktree.

## Agent decisions

In the returned worktree, write or reconcile only the durable design. Use
`dstackctl feature scaffold-design <feature>` when the design file is absent;
it never overwrites an existing design. Decide:

- the user/developer outcome and non-goals;
- existing patterns and reuse, plus why any new abstraction is necessary;
- architecture, interfaces, data flow, and observable success behavior;
- failure, security, compatibility, and migration boundaries;
- validation, including negative behavior and failure recovery; and
- Documentation impact for end users/operators, developers/reviewers, and
  future agents/auditors (each may be `N/A` with a reason).

Create each chosen task mechanically with `dstackctl feature add-task` and use
acceptance criteria stated as observable outcomes, not implementation names.
Do not create `tasks.md`, workflow status docs, a commit solely for starting,
or reviewer/coordinator tasks.

Leave the specification step and human gate open. Return the design path, task
graph, unresolved decisions, and `/review-feature-spec` as the next command.
