---
name: dstack-beads-project-alignment-land
description: "Reconcile and deliver completed project-alignment corrections through the shared safe delivery controller."
---

# Project alignment land

Input includes the audit selector and `ready`, `pr`, or `merge` mode.

1. Run `alignment finish-workstream` and `alignment claim-landing`.
2. Reconcile current repository reality, durable docs, validation, and material remaining findings. Commit only real
   changes with the landing Bead footer. Create a temporary reconciliation with
   `alignment scaffold-record reconciliation --path <file>` and complete every section with substantive evidence or
   `Not applicable — <specific reason>`.
3. Run final review, then `alignment finish-landing --summary-file <file>`. The semantic validator runs before terminal
   mutation; the controller also refuses dirty/untracked work and checks mdBook, docs policy, and correction evidence.
4. Use the same `delivery inspect/pr-preflight/register-pr/finalize-pr/merge` controller as feature delivery.

During normal delivery, Beads finalization must not mutate the delivered Git state or create bookkeeping commits.
Explicit user-authorized recovery after a failed or incorrect delivery is a separate native Git operation. Close the
audit root only after actual delivery.
