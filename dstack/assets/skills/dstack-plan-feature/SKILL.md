---
dstack-managed: true
name: dstack-plan-feature
description: "Plan one feature in Beads and resolve material intent questions."
disable-model-invocation: true
---

# Plan feature

## dStack operations

Use these dStack commands in this stage:

```bash
dstack init
dstack check formula
dstack check plan --bead <root>
```

`dstack init` and `dstack check formula` must succeed before pouring new work. Run the plan check after storing the
completed plan and before closing the plan step.

## Start or resume

If the user supplied a feature root or descendant, resume that molecule; never pour a replacement. Otherwise choose a
stable kebab-case slug and base branch (`dev` when present, otherwise `main`), then pour exactly one `dstack-feature`
molecule with `title`, `desc`, `feature_title`, `feature_slug`, and `base_branch` variables. Label the root
`workflow:feature` and `feature:<slug>`, and set `dstack.base_branch=<base>` metadata.

Inspect `bd mol current <root> --json` and `bd show <plan> --include-comments --json`. A closed plan returns
`/review-plan <root>`; do not reopen it implicitly. Otherwise continue an existing in-progress plan or claim an open
ready plan with:

```bash
bd ready --parent <root> --label dstack:step:plan --claim --json
```

If identity metadata fails after pour, retry that update on the returned root. Do not add another recovery record or
pour another molecule.

## Resolve intent

Planning is intent-focused. Read only enough repository identity to choose the base branch. Do not perform broad source
investigation or memory search; `/review-plan` owns repository and memory reconciliation.

Ask focused questions for material product, architecture, compatibility, operational, or security choices. Record each
question and answer as plan comments. Record `No material questions: <reason>` when none remain. Never silently
choose product policy.

## Store the plan

Put the original request in the plan description, observable outcomes in acceptance criteria, and a publishable mdBook
fragment beginning at heading level three in the design field. The design contains exactly:

```markdown
### Goals
### User-facing behavior
### Implemented design
### Compatibility and constraints
### Validation
### Non-goals
```

Write design content to a temporary file outside the repository, update the Beads fields, delete the temporary file,
then run `dstack check plan --bead <root>`. Do not create implementation tasks or feature documentation during planning.

After validation, close only the plan step and return the root ID, resolved questions, decisions, and
`/review-plan <root>`.
