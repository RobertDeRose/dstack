---
name: dstack-core
description: Shared dstack workflow contracts and conventions. Installed as support for the other dstack skills; use directly when reviewing workflow authority, trust boundaries, or naming conventions.
metadata:
  version: "0.11.3"
allowed-tools: Read Bash
---

# dstack Core Contracts

This support skill contains the shared contracts used by the dstack workflows.

Review orchestration uses [`references/REVIEW-STATE.md`](references/REVIEW-STATE.md) for durable reviewer identity,
source-boundary assignments, resumption, and replacement evidence,
[`references/REVIEW-FINDINGS.md`](references/REVIEW-FINDINGS.md) for current finding dispositions, and the optional
[`references/PI-REVIEWER-ROSTER.md`](references/PI-REVIEWER-ROSTER.md) adapter for mapping logical roles to named Pi
reviewer definitions without changing the tool-agnostic contract. Use `scripts/sync-pi-reviewers.py` only through its
explicit user-selected target; normal skill installation never mutates Pi agent directories.
`build-beads-review-projection.py` supplies execution readiness with a validated transient graph without reading Beads
storage directly, and `append-review-note.py` validates and byte-preserves one-line state/finding JSON across Beads
updates. `promote-legacy-feature.py` attaches the canonical formula lifecycle and a validated implementation plan to an
existing roadmap root without creating a replacement epic.

Lifecycle startup uses [`references/SKILL-VERSION.md`](references/SKILL-VERSION.md) to record the executing installed
skill version and compare it with trustworthy local canonical evidence before mutation. Beads writes and delivery
closure follow [`references/INTERACTION-BOUNDARY.md`](references/INTERACTION-BOUNDARY.md): native linked-worktree
authority is shared, mutation intervals use a repository-scoped lease, foreign interaction evidence remains fail-closed,
and native Dolt publication uses `scripts/guarded-beads-push.py` instead of raw or force pushes.

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
