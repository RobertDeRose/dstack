---
name: dstack-beads-setup-project
description: "Install and validate dStack formula source, with explicit isolated legacy repair when requested."
---

# Setup project

Invoking this command authorizes Beads initialization in the current Git repository. Start with the read-only plan and
review its exact authority, preconditions, and operations. Save the emitted JSON envelope when forced setup is used:

```bash
"{baseDir}/../../bin/dstack" setup plan --root . --init
"{baseDir}/../../bin/dstack" setup apply --root . --init --plan-digest "<plan_sha256>"
```

Append `--force` to both commands only when the user explicitly supplied it. Forced apply also requires the exact saved
plan file:

```bash
"{baseDir}/../../bin/dstack" setup plan --root . --init --force > PLAN.json
"{baseDir}/../../bin/dstack" setup apply --root . --init --force \
  --plan-file PLAN.json --plan-digest "<plan_sha256>"
```

The plan contains one strict `dstack.setup-plan/v4` mutation object. Review its controller/runtime authority,
initialization, Beads, verified template deletion, filesystem, formula, Git-index, and navigation/reference records
rather than relying on display summaries. Forced planning validates the projected documentation tree and mdBook before
Beads mutation. Task trackers, templates, unresolved Markdown, and other ambiguous documentation require disposition;
they are not added to `SUMMARY.md`.

Forced apply consumes the saved plan, creates or reuses a detached migration worktree, targets the contained Beads
runtime explicitly, verifies a native Dolt backup, and retains the plan, backup, and worktree for inspection. It reports
invocation-local Beads command counts and phase durations without persisting them. Do not delete recovery artifacts or
invoke legacy repair a second time.

If setup times out, is interrupted, or reports uncertain mutation, stop. Preserve the retained artifacts and use the
controller's verification or rollback boundary. Never use ad-hoc `bd update`, `bd close`, label changes, manual Git
repair, or documentation edits to reconstruct state. If rollback cannot prove the original Beads and Git state, report
recovery required and do not retry.

For a retained forced migration, verify it with the explicitly selected delivery profile before integration:

```bash
"{baseDir}/../../bin/dstack" setup verify --root . \
  --migration-id "<plan_sha256>" --delivery-mode merge
```

Use `pr` instead when GitHub PR delivery is intended. For ordinary setup, run setup doctor once with the selected
`merge` or `pr` profile. The mode is required and is never inferred from remotes; report the selected mode and every
diagnostic. Do not commit automatically. Ask the user to review and integrate the setup boundary before starting feature
work. Normal feature commands do not run setup doctor or legacy repair.
