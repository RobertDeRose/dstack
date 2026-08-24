# Architecture decisions

Architecture decision records explain durable cross-feature choices and their consequences. Current architecture and
operations pages remain the authority for present behavior. Feature records preserve accepted change intent; ADRs do not
carry transient workflow state.

| ADR | Status | Supersedes | Superseded by |
| --- | --- | --- | --- |
| [0001: Authority ownership](0001-authority-ownership.md) | Accepted | None | None |
| [0002: One-way Git evidence](0002-one-way-git-evidence.md) | Accepted | None | None |
| [0003: Committed-content approval](0003-committed-content-approval.md) | Accepted | None | None |
| [0004: Root open until delivery](0004-root-open-until-delivery.md) | Accepted | None | None |
| [0005: Local interactions and durable documentation](0005-interactions-and-documentation.md) | Accepted | None | None |

An ADR may be `Proposed`, `Accepted`, `Deprecated`, or `Superseded`. A superseding ADR links the prior record, and the
prior record links back. Editing an accepted ADR is limited to clarification and link repair; changed decisions receive
a new record.
