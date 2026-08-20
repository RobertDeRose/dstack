---
name: dstack-beads-review-feature-spec
description: "Review and approve the active or selected feature design without coupling Beads to Git history."
---

# Review feature specification

The selector is optional after `/start-feature`; otherwise use an exact ID,
slug, or title/current `feat/<slug>` worktree.

1. Claim the specification:

   ```bash
   python3 "{baseDir}/../dstack-beads-core/scripts/dstackctl.py" \
     feature claim-spec [selector]
   ```

2. Review the design, task outcomes/dependencies, relevant existing code/docs,
   failure/security/compatibility boundaries, and validation plan. Confirm the
   happy path, invalid/input rejection, state or persistence behavior, failure
   recovery, security boundaries where relevant, and compatibility/regression
   behavior.
3. Confirm `Documentation impact` covers end user/operator, developer/reviewer,
   and future agent/auditor perspectives, allowing `N/A` only with a reason.
4. Resolve clear findings directly. Ask the user only for genuine product or
   architecture decisions.
5. When repository contents changed, commit the actual change with:

   ```bash
   dstackctl.py git commit --bead <spec-id> --subject "<subject>"
   ```

   No commit is required when the accepted design contents were already
   correct.
6. Perform a review of the final boundary. Use a separate reviewer only when
   actually available; do not claim independence otherwise.
7. Approve mechanically:

   ```bash
   dstackctl.py feature approve-spec [selector] [--summary-file <durable.md>]
   ```

This stores only the accepted design-content digest, resolves the human gate,
and closes the approval milestone idempotently. It stores no Git SHA.

Return decisions, material findings, validation expectations, and
`/implement-feature` as the next command.
