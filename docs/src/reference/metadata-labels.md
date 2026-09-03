# Metadata and labels

A feature root carries:

```text
workflow:feature
feature:<slug>
dstack.base_branch=<branch>
```

Formula steps use:

```text
dstack:step:plan
dstack:step:review
dstack:step:approval
dstack:step:implementation
dstack:step:audit
```

Implementation tasks use:

```text
dstack:work:implementation
dstack:commit:<type>
dstack:scope:<optional-scope>
```

Decision Beads use the native `decision` type with searchable feature, area, and concern labels.

Workflow state, readiness, claims, approval, worktree paths, commit IDs, validation results, and next actions stay in
native tools rather than metadata fields.
