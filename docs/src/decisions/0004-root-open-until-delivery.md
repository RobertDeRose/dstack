# 0004: Root open until delivery

- **Status:** Superseded
- **Supersedes:** None
- **Superseded by:** [0006](0006-beads-native-control-plane.md)

## Context

Completing reconciliation is not the same event as delivering repository content. Closing the workflow root before
delivery falsely represents the candidate as shipped.

## Decision

Closeout or landing may complete while the root remains open. The root closes only after direct fast-forward delivery or
confirmed PR delivery. A narrow compatibility helper reopens roots auto-closed by the supported Beads terminal behavior
while awaiting delivery.

## Consequences

Candidate readiness and delivered state remain distinct. Delivery finalization must not create a bookkeeping commit or
mutate delivered Git state. Failed finalization reports observed state and recovers the root when safe.
