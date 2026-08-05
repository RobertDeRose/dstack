---
name: audit-project
description: Audit and reconcile drift across Beads, designs, delivered records, documentation, tests, code, and migration state. Use when asked to audit project consistency, investigate disagreeing artifacts, verify a migration, or prepare for major planning.
metadata:
  version: "0.8.3"
allowed-tools: Read Glob Grep Edit Write Bash Task
---

# Purpose

Use this skill periodically or before major planning cycles to determine whether the project still matches intended
design, documented behavior, delivered-feature history, and live Beads state.

## Shared trust contract

Before executing this workflow, read and follow
[`../dstack-core/references/TRUST-AND-AUTHORITY.md`](../dstack-core/references/TRUST-AND-AUTHORITY.md). That contract is
normative for this workflow. If it conflicts with this skill, follow the more restrictive rule and report the conflict.

## Startup version evidence

Before the first workflow mutation, follow
[`../dstack-core/references/SKILL-VERSION.md`](../dstack-core/references/SKILL-VERSION.md) for `audit-project`. After
read-only inventory work, capture the exact one-line output and record it in the audit evidence before any correction. A
`stale` result warns with `npx skills update`; `unavailable` records that no freshness claim was made and does not block
offline work.

Audit-specific authority:

- Automatic corrections are limited to unambiguous local documentation, navigation, and workflow-state reconciliation.
- Code, API, security-boundary, architecture-policy, or destructive changes require explicit user approval or a
  corrective Beads issue.
- Audit subagents are read-only.

## Execution

## 1. Inventory Sources

Run:

```bash
bd prime
bd list --all --label workflow:feature --json
bd ready --json
bd blocked --json
uv run scripts/check-docs.py
```

Build an inventory row for every `workflow:feature` root containing its lifecycle state, design path, implemented-record
path, roadmap entry, and migration status. Inspect every linked artifact, every durable page in `SUMMARY.md`, and code,
tests, configuration, migrations, and commits changed since the previous audit. Record excluded areas and why. When
`migration/workflow-migration.json` exists, include unresolved migration findings and verify no active feature still
relies on `tasks.md`.

### Git evidence boundary

Recent commit comparison is required audit evidence. Use read-only Git inspection (`git status`, `git log`, `git show`,
and `git diff`) to identify the comparison range and inspect relevant changes. Do not create commits, switch branches,
merge, push, rewrite history, or perform any other Git mutation. A `bd prime` message such as
`Git workflow: stealth mode (no git ops)` does not justify silently omitting this required evidence; it must not be
conflated with the no-branch-push rule in this skill.

If the execution context genuinely forbids even read-only Git inspection, report `audit state: incomplete` and identify
Git evidence as a blocking limitation. Do not describe that evidence as merely excluded and do not claim the audit is
complete. The final report must state either the exact commit range inspected or that the audit is incomplete because
read-only Git evidence was unavailable.

## 2. Compare the System

Check for:

- Beads features missing designs or required delivered records;
- closed features still shown as planned or partial;
- implemented-feature pages without corresponding delivered Beads state;
- code behavior contradicting reader-facing documentation;
- implementation violating documented boundaries or invariants;
- changed design decisions without rationale;
- stale commands, configuration, interfaces, schemas, fields, states, defaults, limits, or terminology;
- tests proving obsolete behavior or failing to cover documented contracts;
- deferred work silently implemented, abandoned, or left blocking;
- duplicate, conflicting, or orphaned feature tasks;
- durable pages missing from `SUMMARY.md`;
- legacy `tasks.md`, include-based feature pages, or unresolved migration status conflicts.

## 3. Classify Drift

Use:

```text
intentional evolution requiring documentation reconciliation
implementation defect
stale documentation
stale feature design or delivery record
workflow-state mismatch
migration-state mismatch
unresolved design decision
missing validation evidence
```

## 4. Record Corrective Work

Apply unambiguous local documentation corrections. Create Beads issues for remaining work, linking them with
`discovered-from`, `related`, or `blocks` as appropriate. Include exact files, evidence, expected resolution, acceptance
criteria, and severity.

For feature-tied drift:

```bash
bd create "Reconcile <finding>" \
  --type task \
  --deps discovered-from:<feature-root-or-task> \
  --labels audit:drift \
  --json
```

Use blocking dependencies only when unresolved drift makes further delivery unsafe.

After corrections, discard validation results made stale by those edits. Rerun `uv run scripts/check-docs.py` and every
affected formatter, linter, build, test, migration, and feature-specific check against the final files. Record exact
commands, outcomes, skipped checks, and limitations. Do not report a correction as verified from a pre-fix result. The
audit is complete only when every finding is corrected and revalidated, linked to a corrective issue, or explicitly
accepted as residual risk.

## 5. Publish Changed Beads State

When the audit creates or updates Beads records, invoking `/audit-project` authorizes one ordinary non-force publication
to the repository's already configured native Dolt remote after final validation:

```bash
bd dolt remote list --json
bd dolt push
```

This authority does not authorize remote creation or replacement, force-pushes, or Git branch pushes. Do not push when
Beads did not change. If no native remote is configured or the push fails, preserve local records and report
`audit publication blocked`; do not claim the corrective work is shared.

Return findings ordered by severity, intentional-versus-accidental classification, files and Beads IDs, corrections
applied, corrective issues created, blocked work, publication evidence, the Git comparison range, and recommended next
action. Include exactly one explicit status line: `audit state: complete` only when all required evidence was inspected
and every finding was corrected, linked to a corrective issue, or explicitly accepted as residual risk; otherwise use
`audit state: incomplete` and name the missing evidence or unresolved work. Beads publication success never changes an
incomplete audit into a complete one. Use this form for the evidence status:

```text
Git evidence: compared <base>..<head> with read-only Git inspection.
Audit state: complete
```

When Git inspection is unavailable, replace the first line with `Git evidence: unavailable — <reason>` and use
`Audit state: incomplete`; do not use a sentence saying that comparison was simply excluded.
