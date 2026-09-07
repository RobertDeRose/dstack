---
dstack-managed: true
name: dstack-plan-feature
description: "Plan one feature in a native Beads molecule and resolve material intent questions."
disable-model-invocation: true
---

# Plan feature

Run only when explicitly invoked. This is an opt-in dStack activation boundary. Beads owns the plan and workflow state;
do not create a parallel plan file in the repository.

## Start or resume

1. Run `dstack init`, then `dstack check formula`. Do not pour new work until committed policy validation succeeds.
2. If the user supplied a feature root or descendant, resume that molecule; never pour a replacement.
3. Otherwise choose a stable kebab-case slug and base branch (`dev` when present, otherwise `main`), then pour exactly
   one `dstack-feature` molecule with `title`, `desc`, `feature_title`, `feature_slug`, and `base_branch` variables.
4. On creation, label the root `workflow:feature` and `feature:<slug>`, and set `dstack.base_branch=<base>` metadata.
5. Inspect `bd mol current <root> --json` and `bd show <plan> --include-comments --json`. Resume this agent's
   in-progress plan without claiming again. A closed plan returns `/review-plan <root>`; do not reopen it implicitly.
   Respect other owners. Only an open, native-ready plan is claimed with
   `bd ready --parent <root> --label dstack:step:plan --claim --json`.

If identity metadata fails after pour, retry that update on the returned root. Do not add feature-creation recovery
logic or pour another molecule.

## Resolve intent

Planning is intent-focused. Read the request and only enough repository identity to select the base branch. Do not
perform broad source investigation or memory search; `/review-plan` owns repository and memory reconciliation.

Ask focused questions for material product, architecture, compatibility, operational, or security choices. Record each
question and answer as native plan comments. Record `No material questions: <reason>` when none remain. Never silently
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

Write design content to a temporary file outside the repository, update the native fields, delete the temporary file,
and run `dstack check plan --bead <plan>`. Do not create implementation tasks or feature documentation during planning.

After validation, close the plan step and return the root ID, resolved questions, decisions, and `/review-plan <root>`.
