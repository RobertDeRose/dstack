---
dstack-managed: true
name: dstack-plan-feature
description: "Plan one feature in a native Beads molecule, asking material questions before finalizing it."
---

# Plan feature

This skill is the dStack workflow activation boundary. Use it only when explicitly invoked. Beads is the workflow
authority once activated; store the plan, questions, answers, decisions, dependencies, and acceptance criteria in Beads.
Do not create a parallel Markdown plan or infer the next phase from repository files.

## Start or resume

1. Initialize and verify the repository's native Beads workspace:

```bash
dstack init
```

This explicit workflow command uses `bd init --skip-agents` only when needed, installs the dStack formula and scoped
`PRIME.md`, and validates the resulting contract. It does not create workflow issues. Do not initialize Beads in stealth
mode or remove existing integrations automatically.

2. When the user supplied an existing feature root or descendant, resume that molecule. Do not pour a replacement.
3. For new work, determine a stable kebab-case slug and the base branch (`dev` when present, otherwise `main`). Pour
   exactly one molecule:

```bash
bd mol pour dstack-feature \
  --var "title=Feature: <title>" \
  --var "desc=<initial request>" \
  --var "feature_title=<title>" \
  --var "feature_slug=<slug>" \
  --var "base_branch=<base>" \
  --json
```

4. Record searchable native identity on the returned root:

```bash
bd update <root> \
  --add-label workflow:feature \
  --add-label feature:<slug> \
  --set-metadata dstack.base_branch=<base> \
  --json
```

The `feature:<slug>` label is the sole slug authority. If the update fails after pouring, retain the returned root ID
and retry this exact update; do not pour another molecule.

5. Claim the native plan step:

```bash
bd ready --parent <root> --label dstack:step:plan --claim --json
```

If it is already claimed by this session, resume it. Never claim a different workflow step merely because it is also
visible.

## Investigate before asking

Read only the current code, tests, governing documentation, and prior decision Beads needed to understand the requested
outcome. Search decision Beads by relevant component or concern labels before scanning current repository documentation.

Perform an explicit ambiguity pass. Classify each uncertainty as:

- resolved by repository evidence;
- a safe implementation detail;
- a material product, architecture, compatibility, operational, or security question.

Ask material questions one at a time before finalizing the plan. Do not silently choose product policy. Record every
asked question and answer in the plan as paired `Question:` and `Answer:` lines. When repository evidence establishes
that no user decision is required, record `No material questions: <specific evidence-based reason>` instead.

## Store the plan

Write the final plan to a temporary file outside the repository and update the plan Bead's native `design` field. The
plan must contain these sections:

```markdown
## Goal

## Current behavior

## Proposed behavior

## Repository evidence

## Questions and answers

## Decisions and rationale

## Compatibility

## Documentation impact

### End users

### Developers

### Future agents

## Non-goals
```

Store observable acceptance criteria in the Bead's native acceptance field. The documentation sections must identify
current documentation that must change or explain why that audience is unaffected. Future-agent impact covers current
architecture/invariant documentation and searchable decision Beads, not a second workflow ledger.

```bash
bd update <plan-bead> \
  --design-file <temporary-plan> \
  --acceptance '<observable criteria>' \
  --json

dstack ctl plan check <plan-bead>
```

Remove the temporary file after validation. Fix structural failures before closing the plan Bead. Do not create
implementation tasks during planning.

When validation passes:

```bash
bd close <plan-bead> --reason 'Feature plan completed'
```

Return the molecule root, material questions and answers, final decisions, and `/review-plan <root>` as the next action.
