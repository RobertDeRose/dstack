---
name: dstack-beads-implement-feature
description: "Claim native ready feature work, implement it, and complete it with rewrite-safe Git evidence."
---

# Implement feature

The feature selector is optional after `/start-feature`. Accept an optional task
ID or `--all`; default to one task.

For each task:

1. Claim native ready work:

   ```bash
   python3 "{baseDir}/../dstack-beads-core/scripts/dstackctl.py" \
     feature claim-next [feature] [--task <id>]
   ```

   This verifies the approved design digest and uses Beads' atomic ready claim.
2. Read the selected Bead, accepted design, relevant source/tests/docs, and only
   the context needed to decide the implementation.
3. Implement the smallest correct solution. Update durable docs when behavior or
   design requires it. Run focused and repository-required validation.
4. Review the committed candidate. Correct material findings; ask only for a
   genuine intent decision. Persist a summary only when it contains durable
   evidence.
5. Stage the intended task boundary and commit through:

   ```bash
   dstackctl.py git commit --bead <task-id> --subject "<subject>"
   ```

6. Complete the task mechanically:

   ```bash
   dstackctl.py feature finish-task <feature> --task <task-id>
   ```

`--all` repeats until no native ready implementation task remains. It does not
parallelize writers. Do not create bookkeeping commits or Git-SHA mappings.
