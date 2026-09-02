# Architecture decisions

Architecture decision records preserve durable rationale. Current architecture and operations pages remain authoritative
for present behavior; native Beads history carries workflow chronology.

| ADR | Status | Supersedes | Superseded by |
| --- | --- | --- | --- |
| [0001: Authority ownership](0001-authority-ownership.md) | Accepted | None | None |
| [0002: One-way Git evidence](0002-one-way-git-evidence.md) | Accepted | None | None |
| [0003: Committed-content approval](0003-committed-content-approval.md) | Superseded | None | 0006 |
| [0004: Root open until delivery](0004-root-open-until-delivery.md) | Superseded | None | 0006 |
| [0005: Local interactions and durable documentation](0005-interactions-and-documentation.md) | Superseded | None | 0006 |
| [0006: Beads-native control plane](0006-beads-native-control-plane.md) | Accepted | 0003, 0004, 0005 | None |

An ADR may be `Proposed`, `Accepted`, `Deprecated`, or `Superseded`. Changed decisions receive a new record rather than
rewriting historical rationale.
