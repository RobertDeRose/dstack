---
name: dstack-beads-project-alignment-execute
description: "Approve and execute native ready project-alignment corrections against current repository evidence."
---

# Project alignment execute

Explicit invocation authorizes Tier 2 corrections, not delivery.

1. Run `dstackctl.py alignment approve <audit>` idempotently.
2. Claim one correction with `alignment claim-next` (or repeat for `--all`).
3. Revalidate the finding against the repository as it exists now. If already fixed or obsolete, update/close the Bead
   with the concrete reason instead of implementing stale instructions.
4. Otherwise decide and implement the smallest correct correction, validate, review, and commit through
   `dstackctl.py git commit --bead <id>`.
5. Complete each correction with `alignment finish-task`. This never closes the workstream implicitly. After all
   required corrections are closed or explicitly deferred, run `alignment finish-workstream` once.

Do not deliver, create a PR, or store Git SHAs in Beads.
