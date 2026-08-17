---
name: dstack-beads-project-alignment-land
description: "Reconcile and deliver completed project-alignment corrections through the shared safe delivery controller."
---

# Project alignment land

Input includes the audit selector and `ready`, `pr`, or `merge` mode.

1. Run `alignment finish-workstream` and `alignment claim-landing`.
2. Reconcile current repository reality, durable docs, validation, and material
   remaining findings. Commit only real changes with the landing Bead footer.
3. Run docs policy and final review, then `alignment finish-landing`.
4. Use the same `delivery inspect/pr-preflight/register-pr/finalize-pr/merge`
   controller as feature delivery.

No post-delivery Git mutation or bookkeeping commit is allowed. Close the audit
root only after actual delivery.
