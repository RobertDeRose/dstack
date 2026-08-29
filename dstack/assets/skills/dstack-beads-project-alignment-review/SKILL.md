---
name: dstack-beads-project-alignment-review
description: "Analyze current project alignment and prepare a gated corrective plan without modifying repository source."
---

# Project alignment review

Tier 1 is read-only for repository source.

1. Initialize or inspect the audit:

   ```bash
   dstack ctl alignment initialize --title "<title>" \
     --target-branch <branch> --scope "<scope>"
   ```

2. Compare current specifications, durable docs, architecture patterns, code, tests, Beads work, and delivery evidence.
   Treat the current repository and Beads records as the review inputs; do not persist a Git baseline.
3. Decide bounded corrective outcomes, acceptance criteria, priorities, and real dependencies. Create code/test
   corrections with `alignment add-correction`; do not create documentation or reconciliation tasks because landing is
   the sole final reconciliation.
4. Create temporary `PLAN.json`. Use a canonical JSON plan helper exposed by the current CLI when available; otherwise
   write the file directly. Markdown record scaffolds are not authoritative plan input.
5. Populate exactly `dstack.alignment-plan/v2`:
   - `schema`: `dstack.alignment-plan/v2`;
   - `scope`;
   - `findings`: `{title, evidence, rationale}` objects;
   - `accepted_corrections`: `{title, description, acceptance, priority, depends_on}` objects whose dependency values
     are accepted correction titles;
   - `rejected_corrections`: `{title, rationale}` objects;
   - `validation_expectations`: strings;
   - `documentation_impact`: exactly `end_user_operator`, `developer_reviewer`, and `future_auditor` string arrays;
   - `deferred_findings`: `{title, rationale}` objects; and
   - `accepted_risks`: `{title, rationale}` objects.

   Include every field, use `[]` for an empty collection, and add no other keys.
6. Finish the canonical plan and stop with the human gate open:

   ```bash
   dstack ctl alignment finish-plan AUDIT --plan-file PLAN.json
   ```

   The controller validates, canonicalizes, stores, rereads, and binds the plan before any authorization state closes.

Return findings, correction graph, decisions required, and `/project-alignment-execute <audit>`.
