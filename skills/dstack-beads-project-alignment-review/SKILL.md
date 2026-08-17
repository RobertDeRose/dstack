---
name: dstack-beads-project-alignment-review
description: "Analyze current project alignment and prepare a gated corrective plan without modifying repository source."
---

# Project alignment review

Tier 1 is read-only for repository source.

1. Initialize or inspect the audit:

   ```bash
   dstackctl.py alignment initialize --title "<title>" \
     --target-branch <branch> --scope "<scope>"
   ```

2. Compare current specifications, durable docs, architecture patterns, code,
   tests, Beads work, and delivery evidence.
3. Decide bounded corrective outcomes, acceptance criteria, priorities, and real
   dependencies. Create them with `alignment add-correction`.
4. Do not store a baseline Git SHA. The plan records concrete current evidence;
   Tier 2 revalidates it before mutation.
5. Finish the plan with `alignment finish-plan` and stop with the human gate
   open.

Return findings, correction graph, decisions required, and `/project-alignment-execute <audit>`.
