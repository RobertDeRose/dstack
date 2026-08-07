---
name: dstack-core
description: Shared dstack workflow contracts and conventions. Installed as support for the other dstack skills; use directly when reviewing workflow authority, trust boundaries, or naming conventions.
metadata:
  version: "0.8.5"
allowed-tools: Read Bash
---

# dstack Core Contracts

This support skill contains the shared contracts used by the dstack workflows.

Review orchestration uses [`references/REVIEW-STATE.md`](references/REVIEW-STATE.md) for durable reviewer identity,
packet/source boundaries, resumption, and replacement evidence, and
[`references/REVIEW-FINDINGS.md`](references/REVIEW-FINDINGS.md) for current finding dispositions.

Lifecycle startup uses [`references/SKILL-VERSION.md`](references/SKILL-VERSION.md) to record the executing installed
skill version and compare it with trustworthy local canonical evidence before mutation.

Before executing a dstack workflow that links to a reference in this directory, read that reference completely. The
calling skill remains responsible for its workflow-specific authority and completion rules.

## Feature resolution

`<core-dir>/scripts/resolve-feature.py` resolves feature epics through Beads by canonical slug, exact or unique human
name, or ID. Use `--next` to select the next ready feature epic. Workflow commands should expose the canonical `<slug>`
reference and retain the Beads ID only for mutations and audit evidence.

Standalone executable issues use `/implement-task <task-selector>`. It processes exactly one open `task`, `bug`,
`chore`, `spike`, or standalone `feature`; feature epics and their descendants remain owned by the feature lifecycle.
`verify-delivery-state.py` provides the post-merge semantic check used by `/close-feature` to reconcile delivery claims
with the actual base-branch commit.
