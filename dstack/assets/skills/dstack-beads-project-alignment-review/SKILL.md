---
dstack-managed: true
name: dstack-beads-project-alignment-review
description: "Analyze current project alignment and prepare a gated corrective plan without modifying repository source."
---

# Project alignment review

Tier 1 is read-only for repository source.

1. Initialize or inspect the audit with
   `dstack ctl alignment initialize --title "<title>" --target-branch <branch> --scope "<scope>"`.
2. Compare current specifications, durable docs, architecture patterns, code, tests, Beads work, and delivery evidence.
   Treat Git and Beads as the authorities; do not create a packet or duplicate correction state in a file.
3. Create only accepted code/test corrections with `dstack ctl alignment add-correction`. Put descriptions, acceptance
   criteria, priorities, and real dependencies directly in Beads. Landing owns final documentation reconciliation.
4. Write a concise human-readable review summary to a temporary Markdown file outside the repository. Record findings,
   rejected/deferred findings, accepted risks, validation expectations, and documentation impact. Do not repeat complete
   correction definitions already stored in Beads.
5. Finish the review with `dstack ctl alignment finish-plan AUDIT --summary-file <temporary-summary>`. The controller
   derives approval authority from the summary and exact native correction graph, then stops with the human gate open.

Return the findings, correction graph, decisions required, and `/project-alignment-execute <audit>`.
