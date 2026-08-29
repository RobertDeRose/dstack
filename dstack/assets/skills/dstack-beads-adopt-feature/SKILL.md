---
name: dstack-beads-adopt-feature
description: "Adopt one active legacy dStack feature through a narrow stateless compatibility transition."
---

# Adopt feature

This authorizes Beads adoption mutations only—no source, Git-history, branch, or worktree changes.

1. Inspect and classify obvious legacy nodes:

   ```bash
   dstack ctl adopt inspect <legacy-feature>
   ```

2. Decide every open executable descendant, including bug/chore work, and write one temporary strict
   `dstack.adoption-classification/v1` JSON file. The file must contain the common `legacy_root_id`, one sorted entry
   per open executable item, exact replacement content where needed, durable evidence for completed history, and an
   explicit unresolved-decision or preserved-work strategy. Do not use Beads IDs as a persisted migration map. Bug/chore
   work is inventoried, but an unsupported approval or root-remap topology fails closed rather than emitting a
   cross-type blocker.
3. Validate the complete plan before allowing native mutation:

   ```bash
   dstack ctl adopt plan <legacy-feature> \
     --classification-file CLASSIFICATION.json
   ```

4. Apply the same classification file only after reviewing the emitted plan:

   ```bash
   dstack ctl adopt apply <legacy-feature> \
     --classification-file CLASSIFICATION.json
   ```

The controller validates descendants, gates, both graph directions, evidence, replacement topology, and canonical design
sections before pouring a current molecule. Native execution creates/reuses replacements first, adds translated
relationships before removing old edges, records explicit accepted-risk comments, and vetoes root supersession when
decisions or preserved work remain unsafe. Retries reconstruct native state; no migration packet, SHA mapping, or dStack
migration database is created.

Return the new root/steps, selected remaining work, ambiguous decisions, and `/review-feature-spec <slug>`.
