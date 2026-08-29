---
dstack-managed: true
name: dstack-beads-adopt-feature
description: "Adopt one active legacy dStack feature through a narrow stateless compatibility transition."
---

# Adopt feature

This authorizes Beads adoption mutations only—no source, Git-history, branch, or worktree changes.

1. Run `dstack ctl adopt inspect <legacy-feature>` and review the returned native inventory and suggested categories.
2. Classify every open executable descendant with explicit `adopt apply` selections. Common selections are
   `--remaining ID`, `--spec-ceremony ID`, `--implementation-coordinator ID`, `--closeout-ceremony ID`, and
   `--preserve ID`. The inspect output lists the less common reparent, recreate, decision, and completed-history forms.
3. Run one `dstack ctl adopt apply <legacy-feature> <selections...>`. Do not create a classification packet. The
   controller validates the selections against one current graph snapshot before mutation and rejects omitted,
   duplicate, foreign, or drifted work.

The controller creates or reuses replacements first, adds translated relationships before removing obsolete edges, and
vetoes root supersession while decisions or preserved work remain unsafe. Return the new root/steps, selected remaining
work, ambiguous decisions, and `/review-feature-spec <slug>`.
