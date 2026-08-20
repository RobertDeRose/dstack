---
name: dstack-beads-close-feature
description: "Reconcile a completed feature and deliver it safely without post-delivery Git bookkeeping."
---

# Close feature

Input is an optional feature selector and mode: `ready` (default), `pr`, or
`merge`.

## Closeout

1. Close the implementation workstream when all required children are complete:

   ```bash
   dstackctl.py feature finish-workstream [feature]
   dstackctl.py feature claim-closeout [feature]
   ```

2. Compare accepted design, actual code/tests, durable docs, decisions, and
   required validation. Reconcile real behavior and documentation. Confirm tests
   prove externally meaningful behavior, invariants, failure handling, and
   regression boundaries. Reconcile every declared Documentation impact surface
   for end users/operators, developers/reviewers, and future agents/auditors.
   Allowed docs describe what is planned/implemented, why, and how; they must
   not contain transient workflow state or IDs.
3. Run validation and review. Commit only real code/docs changes with the
   closeout Bead footer.
4. Run the documentation policy guard against the target and candidate, then:

   ```bash
   dstackctl.py feature finish-closeout [feature]
   ```

## Delivery

- `ready`: run `dstackctl.py delivery inspect <feature>` and stop with the root open.
- `pr`: run `delivery pr-preflight`; draft title/body from the complete commit series and aggregate diff; obtain user
  approval; save the approved body and rerun preflight with `--title` and `--body-file`; only then push/create the PR
  and run `delivery register-pr --pr-number <n>`. On later invocation run `delivery finalize-pr`.
- `merge`: run `delivery merge`.

The controller requires linear ancestry, synchronized PR base state, clean
worktrees, and no transient-doc violations. After delivery begins it snapshots
Git, finalizes Beads, and fails if tracked Git state changes. Never create a
post-merge status commit.
