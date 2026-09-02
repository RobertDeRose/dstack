# Metadata and labels

The native feature root carries stable identity only:

```text
workflow:feature
feature:<slug>
dstack.feature_slug=<slug>
dstack.base_branch=<branch>
```

Formula steps use labels:

```text
dstack:step:plan
dstack:step:review
dstack:step:approval
dstack:step:implementation
dstack:step:audit
```

Reviewed implementation work uses:

```text
dstack:work:implementation
dstack:commit:<type>
dstack:scope:<optional-scope>
```

Decision Beads use the native `decision` type and searchable feature/area/concern labels.

Do not store phase, readiness, current task, pending approval, worktree path, commit SHA, validation cache, audit
result, or next-command metadata. These facts are native or reconstructible.
