---
name: dstack-beads-setup-project
description: "Install and validate dStack formula source, with explicit isolated legacy repair when requested."
---

# Setup project

Invoking this command authorizes Beads initialization in the current Git repository.

Run the read-only plan, review its exact preconditions and changes, then apply from freshly recomputed authority state:

```bash
python3 "{baseDir}/../dstack-beads-core/scripts/setup.py" \
  plan --root . --init
python3 "{baseDir}/../dstack-beads-core/scripts/setup.py" \
  apply --root . --init --plan-digest "<plan_sha256>"
```

Replace `<plan_sha256>` with the digest emitted by the reviewed plan. Append
`--force` to both commands only when the user explicitly supplied it.
When `--force` was requested, apply first migrates mechanically identifiable legacy book
content into `docs/src`, then completes the non-destructive documentation
foundation/navigation, performs the remaining isolated compatibility repair,
and finally runs strict documentation validation. Do not invoke repair a second
time.

Finally run the setup doctor once:

```bash
python3 "{baseDir}/../dstack-beads-core/scripts/setup.py" doctor --root .
```

Report formula install/validation, Beads version, canonical mdBook foundation
creation/validation, the local interaction-log policy, missing historical
feature reconciliations, applied documentation moves/reference rewrites, and
other compatibility repair. Report ambiguous Markdown that cannot be placed in
the book mechanically; leave it for user/agent judgment. Do not commit
automatically. Ask the user to review and commit the setup boundary before
starting feature work.
Normal feature commands do not run setup doctor or legacy repair.
