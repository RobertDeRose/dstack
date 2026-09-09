# Project audit

`/audit-project` is an explicit repository-wide drift review. It is separate from `/close-feature`, which reviews one
approved feature before documentation publication.

Project audit compares current source, tests, documentation, security and operations guidance, accepted decisions, and
the repository's validation result. It searches only relevant Beads memory. Current repository documentation and
accepted decisions outrank stale memory, and memory changes require user approval.

If no actionable drift exists, the command reports its evidence without creating workflow state. If remediation is
needed, it creates one normal feature, records the findings and accepted intent in its plan, validates and closes only
that plan step, and returns the feature root for `/review-plan`.

Project audit does not bypass review, approval, implementation, or close.
