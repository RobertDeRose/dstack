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

During normal delivery, Beads finalization must not mutate the delivered Git state or create bookkeeping commits.
Explicit user-authorized recovery after a failed or incorrect delivery is a separate native Git operation. Close the
audit root only after actual delivery.
