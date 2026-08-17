# Review policy

A review supplies evidence; it does not own workflow authority.

Use these outcomes:

- **changes requested** — fixable inside accepted scope;
- **decision required** — accepted product/architecture intent must change;
- **validation pending** — required evidence belongs in another environment;
- **review unavailable** — usable review evidence was not produced;
- **approved** — no unresolved material finding remains;
- **accepted risk** — explicitly accepted unresolved risk.

A new bug or missing assertion is not redesign. There is no pass counter. Explicit user authorization always permits
another review.

Call a review independent only when a separate read-only agent/session performs it. Otherwise call it a review.

By default, persist at most one final review summary. Add an intermediate comment only for a durable decision, accepted
risk, deferred validation, separate material work, or unavailable review that changes execution.
