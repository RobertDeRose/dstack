---
name: dstack-beads-setup-project
description: "Install and validate dStack formula source, with explicit isolated legacy repair when requested."
---

# Setup project

Invoking this command authorizes Beads initialization in the current Git repository.

Run the read-only plan, review its exact preconditions and changes, then apply from freshly recomputed authority state:

```bash
"{baseDir}/../../bin/dstack" setup plan --root . --init
"{baseDir}/../../bin/dstack" setup apply --root . --init --plan-digest "<plan_sha256>"
```

Replace `<plan_sha256>` with the digest emitted by the reviewed plan. The plan contains one strict
`dstack.setup-plan/v3` mutation object; review its controller/runtime authority, initialization, Beads, filesystem,
formula, Git-index, and navigation/reference records rather than relying on display summaries. Append `--force` to both
commands only when the user explicitly supplied it. Apply recomputes the same object once and fails closed if its digest
or any source/precondition changed. When `--force` was requested, apply first migrates mechanically identifiable legacy
book content into `docs/src`, then completes the non-destructive documentation foundation/navigation, performs the
remaining isolated compatibility repair, and finally runs strict documentation validation. Do not invoke repair a second
time.

Finally run the setup doctor once with the explicitly selected delivery profile (use `merge` for local/direct delivery
or `pr` when GitHub PR delivery is intended):

```bash
"{baseDir}/../../bin/dstack" setup doctor --root . --delivery-mode merge
```

The mode is required; never infer it from remotes. Merge mode does not require a remote, GitHub, or `gh`. PR mode
additionally checks a usable GitHub target remote, GitHub CLI authentication, and native Beads `gh:pr` gate capability.
Report the selected mode and every diagnostic.

Report formula install/validation, Beads version, canonical mdBook foundation creation/validation, the local
interaction-log policy, missing historical feature reconciliations, applied documentation moves/reference rewrites, and
other compatibility repair. Report ambiguous Markdown that cannot be placed in the book mechanically; leave it for
user/agent judgment. Do not commit automatically. Ask the user to review and commit the setup boundary before starting
feature work. Normal feature commands do not run setup doctor or legacy repair.
