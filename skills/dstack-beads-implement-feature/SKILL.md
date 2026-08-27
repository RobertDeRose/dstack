---
name: dstack-beads-implement-feature
description: "Claim native ready feature work, implement it, and complete it with rewrite-safe Git evidence."
---

# Implement feature

Pass the selected authorized feature root explicitly; omission is safe only from its registered feature worktree. Accept
an optional task ID or `--all`; default to one task.

For each task:

1. Inspect and claim native ready work:

   ```bash
   "{baseDir}/../../bin/dstack" ctl feature claim-next [feature] [--task <id>]
   ```

   This verifies the approved design digest and uses Beads' atomic ready claim.
2. Read the selected Bead, accepted design, relevant source/tests/docs, and only the context needed to decide the
   implementation.
3. Implement the smallest correct solution. Update durable docs when behavior or design requires it. Run focused
   validation and any additional check required by the accepted task. Tests should prove externally meaningful behavior,
   invariants, failure handling, and regression boundaries rather than private structure. Keep the declared
   Documentation impact surfaces consistent.
4. Treat validation as incomplete when a required check fails, times out, is interrupted, runs the wrong scope,
   unexpectedly skips required tests, or is replaced by weaker coverage. When incomplete, report the exact command,
   scope, and outcome, then stop before commit or task completion. Persist a Beads comment only when missing evidence
   must survive the session and is not otherwise derivable.
5. Review the complete candidate diff before staging. Correct material findings and rerun affected checks; ask only for
   a genuine intent decision.
6. Stage only the intended task boundary and commit through:

   ```bash
   "{baseDir}/../../bin/dstack" ctl git commit --bead <task-id> --subject "<subject>"
   ```

7. Verify the committed footer and changed paths before completion:

   ```bash
   "{baseDir}/../../bin/dstack" ctl evidence commits --bead <task-id> --ref <base>..HEAD
   "{baseDir}/../../bin/dstack" ctl feature finish-task <feature> --task <task-id>
   ```

`--all` repeats only over native ready implementation tasks. When none remain, report completion and stop. Do not run
`feature finish-workstream`, claim or run closeout, load `/close-feature`, or invoke delivery; those require a separate
user command. Do not parallelize writers or create bookkeeping commits or Git-SHA mappings.
