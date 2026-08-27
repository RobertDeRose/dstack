---
name: dstack-beads-close-feature
description: "Reconcile a completed feature and deliver it safely without post-delivery Git bookkeeping."
---

# Close feature

Pass the selected authorized feature root explicitly; omission is safe only from its registered feature worktree. Input
mode is `ready` (default), `pr`, or `merge`.

## Closeout

1. Close the implementation workstream when all required children are complete:

   ```bash
   "{baseDir}/../../bin/dstack" ctl feature finish-workstream [feature]
   "{baseDir}/../../bin/dstack" ctl feature claim-closeout [feature]
   "{baseDir}/../../bin/dstack" ctl feature scaffold-reconciliation [feature]
   ```

2. Compare accepted design, actual code/tests, durable docs, decisions, and required validation. Reconcile real behavior
   and documentation. Confirm tests prove externally meaningful behavior, invariants, failure handling, and regression
   boundaries. Reconcile every declared Documentation impact surface for end users/operators, developers/reviewers, and
   future agents/auditors. Allowed docs describe what is planned/implemented, why, and how; they must not contain
   transient workflow state or IDs. Complete every reconciliation scaffold section with substantive content or
   `Not applicable — <specific reason>`; placeholders, duplicate/missing headings, and unsupported local links fail
   before closeout mutation.
3. Run the repository's full/release validation and review the complete candidate diff. If a required check fails, times
   out, is interrupted, runs the wrong scope, unexpectedly skips required tests, or substitutes weaker coverage, report
   the exact command, scope, and outcome and stop before `feature finish-closeout` or delivery. Correct material
   findings, rerun affected checks, and commit only real code/docs changes with the closeout Bead footer.
4. Validate the current mdBook and run the documentation policy guard against the target and candidate, then:

   ```bash
   "{baseDir}/../../bin/dstack" ctl docs validate
   "{baseDir}/../../bin/dstack" ctl feature finish-closeout [feature]
   ```

## Delivery

- `ready`: run `"{baseDir}/../../bin/dstack" ctl delivery inspect <feature>` and stop with the root open.
- `pr`: run `delivery pr-preflight`; draft title/body from the complete commit series and aggregate diff; obtain user
  approval; save the approved body and rerun preflight with `--title` and `--body-file`; only then push/create the PR
  and run `delivery register-pr --pr-number <n>`. On later invocation run `delivery finalize-pr`.
- `merge`: run `delivery merge`.

The controller requires linear ancestry, synchronized PR base state, clean worktrees, and no transient-doc violations.
During normal delivery, Beads finalization must not mutate the delivered Git state or create bookkeeping commits.
Explicit user-authorized recovery after a failed or incorrect delivery is a separate native Git operation.
