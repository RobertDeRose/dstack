# Project audit

`/audit-project` is an explicit, repository-wide drift review. It is separate from `/close-feature`, which reviews one
approved feature before publication.

Project audit searches only relevant Beads memories and compares them with current code, tests, documentation, security
and operations guidance, accepted decisions, and the repository's documented validation result. Current documentation
and accepted decisions outrank stale memory. Memory changes require user approval.

If no actionable drift exists, audit reports evidence without creating work. If remediation is needed, it pours one
normal feature molecule, records the findings and accepted intent in its plan, validates and closes only that plan step,
and returns the root for `/review-plan`. It does not bypass review, approval, implementation, or close.
