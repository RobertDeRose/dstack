# Metadata and labels

The native feature root carries one searchable slug authority and one execution hint:

```text
workflow:feature
feature:<slug>
dstack.base_branch=<branch>
```

Older roots may also contain `dstack.feature_slug`; dStack accepts it only when it agrees with the `feature:<slug>` label.
New workflows do not write it.

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

Concrete tasks are created with `--no-inherit-labels`, so the structural implementation-step label never leaks onto
work items. Decision Beads use the native `decision` type and searchable feature/area/concern labels.

Do not store phase, readiness, current task, pending approval, worktree path, commit SHA, validation cache, audit result,
or next-command metadata. These facts are native or reconstructible.
