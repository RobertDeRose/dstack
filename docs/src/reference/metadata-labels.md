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

Implementation tasks use only the discovery label:

```text
dstack:work:implementation
```

Commit type and scope are derived from the fixed feature contract rather than task metadata. Ordered native
`Implementation:` notes record delivered work and supply implementation commit bullets. Each note is a concise,
verb-led, one-line fragment of no more than 96 characters; dStack strips surrounding whitespace and punctuation before
adding `- ` without wrapping. Planned task description and design are not commit evidence. Legacy labels may remain on
tasks created by a workflow already active during the
transition, but new tasks do not require them.

Decision Beads use the native `decision` type with searchable feature, area, and concern labels.

Workflow state, readiness, claims, approval, worktree paths, commit IDs, validation results, and next actions stay in
native tools rather than metadata fields.
