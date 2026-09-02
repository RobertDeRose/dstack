# Documentation

Documentation is current product work, not a delayed closeout activity.

## Audiences

Every implementation task classifies its effect on three audiences.

### End users

Document user-visible behavior, configuration, installation, deployment,
operations, migration, failure handling, and troubleshooting where applicable.

### Developers

Document architecture, interfaces, data flow, invariants, extension points, test
strategy, and important implementation constraints.

### Future agents

Make current architecture and invariants discoverable in canonical repository
documentation. Record material historical rationale, rejected alternatives, and
consequences as searchable decision Beads linked to the feature and affected
area.

## Task contract

A task description contains:

```markdown
## Documentation impact

- End-user: required - <specific effect and location>
- Developer: not affected - <specific reason>
- Future-agent: required - <invariant or decision record affected>
```

Every audience is mandatory. `not affected` requires a meaningful reason.
Documentation updates belong in the same task as the behavior they describe or,
when a change spans several tasks, in an explicitly dependent implementation
task—not in an implicit final phase.

## What is not documentation authority

Do not use repository Markdown for live task status, the next command, claims,
worktree paths, commit mappings, approval state, or handoff packets. Beads owns
those workflow facts. Historical feature records may remain as archive material,
but agents should query decision Beads and current docs before scanning them.
