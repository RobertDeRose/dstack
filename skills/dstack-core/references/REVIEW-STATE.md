# Durable review state

Review sessions are ephemeral, but review authority is durable Beads state. Every feature review record and every
standalone task appends machine-readable state before launch and after each transition. The last state for a reviewer is
current; earlier records remain audit history.

## Executable authority

`../scripts/review-state.py` is the pure stdlib authority for validation, legal transitions, v1 migration, and aggregate
gate projection. It reads JSON on stdin, writes JSON on stdout, never mutates Beads or Git, and exits 2 with
`dstack.review-state-error.v1` for malformed state or illegal edges.

```bash
python3 ../scripts/review-state.py validate < state.json
python3 ../scripts/review-state.py transition < event.json
python3 ../scripts/review-state.py aggregate < reviewers.json
python3 ../scripts/review-state.py migrate-v1 < legacy-v1.json
python3 ../scripts/review-state.py migrate-v2 < legacy-v2.json
```

Workflow controllers persist helper output in Beads notes with the `Review state:` prefix. They must not recreate
transition policy from prose or reviewer wording.

## State schema v3

`dstack.review-state.v3` records:

- `reviewer_id`: stable logical reviewer identity;
- `review_issue_id`: owning Beads review issue; Beads remains the manifest and durable owner;
- `state`: current state from the table below;
- `pass`: `initial` or `verification`;
- `pending_conditions`: compound decision, findings, waiver, incomplete, or redesign conditions;
- `declared_domains`, `declared_paths`, and `declared_requirement_ids`: aggregate invalidation boundary;
- `review_boundary_id`, `reviewed_commit`, `reviewed_diff_base`, and `reviewed_diff_digest`: immutable Git source
  boundary;
- validated `current_findings`, complete decision evidence, exact waiver scope, and preserved partial evidence;
- `redesign_replacement_count`: zero or one per design boundary;
- `infrastructure_replacement_count`: independent zero-or-one counters for initial and verification passes; and
- `telemetry`: assignment path/domain counts when available, elapsed time, context usage, terminal status, and
  replacement cause. Telemetry is operational evidence, never approval.

Packet and projection identities are retired from executable v3 state. Historical packet-era records may remain in Beads
notes, but they never authorize a redesigned boundary or aggregate approval. `migrate-v2` validates a packet-era v2
record, preserves it under `legacy_state`, and produces active non-approving v3 state without importing findings,
decisions, waivers, counters, or approval.

Validation enforces state/pass/pending/provisional coherence, validates decision answers against the current
`reviewed_diff_digest`, and retains resolved decision evidence. Active states must have no findings, unresolved
decision, or waiver evidence; approval never clears such evidence. An aggregate requires one unique reviewer for every
exact `required_reviewer_id`; fabricated approval, omitted/duplicate reviewers, or waiver without eligible findings and
complete evidence fails.

The durable wrapper record may retain reviewer session identity, source-boundary evidence, review round, supersession,
and unavailability evidence. A v1 or packet-era wrapper may remain in audit history; new executable decisions use the v3
source-bound state.

## Per-reviewer transitions

| Current state             | Event                                                           | Next state                                        |
|---------------------------|-----------------------------------------------------------------|---------------------------------------------------|
| `initial_active`          | approve                                                         | provisional `approved`                            |
| `initial_active`          | findings                                                        | `changes_required`                                |
| `initial_active`          | unresolved intent                                               | `decision_required`                               |
| `initial_active`          | findings plus unresolved intent                                 | compound `decision_required` + `changes_required` |
| `initial_active`          | timeout/unavailable                                             | `initial_incomplete`                              |
| `initial_incomplete`      | explicit retry with unused initial infrastructure counter       | `initial_active`                                  |
| `initial_incomplete`      | retry after counter is spent                                    | `redesign_required`                               |
| decision/findings state   | all pending answer/fixes persisted                              | `verification_active`                             |
| `verification_active`     | approve                                                         | `approved`                                        |
| `verification_active`     | eligible non-material findings                                  | `waiver_required`                                 |
| `verification_active`     | material or protected finding                                   | `redesign_required`                               |
| `verification_active`     | timeout/unavailable                                             | `verification_incomplete`                         |
| `verification_incomplete` | explicit retry with unused verification infrastructure counter  | `verification_active`                             |
| `verification_incomplete` | retry after counter is spent                                    | `redesign_required`                               |
| `waiver_required`         | user accepts eligible findings with evidence                    | `approved_with_waiver`                            |
| `waiver_required`         | user declines                                                   | `redesign_required`                               |
| `redesign_required`       | `redesign` with unused redesign counter and new source boundary | `initial_active`                                  |

Every unlisted edge fails. There is no third pass on one review boundary. A `redesign` event starts a new boundary
rather than adding another pass to the old one.

## Compound reports and aggregate coordination

State is per reviewer. A controller-owned `dstack.review-aggregate.v2` projection combines current reviewer records.
`spec-reconcile` or another owning gate closes only when every required reviewer is `approved` or
`approved_with_waiver`.

A report may contain both unresolved intent and ordinary findings. Verification cannot begin until the decision answer
and all fixes are persisted. Initial approval is provisional: if sibling reconciliation overlaps a declared path,
domain, or requirement, aggregate reconciliation atomically applies one common Git source boundary to every reviewer,
records the complete change set, invalidates approval, and starts that reviewer's verification pass. No assignment or
projection identity is durable. Partial boundary updates are rejected. Disjoint changes do not invalidate it. An overlap
after verification is terminal `redesign_required`; it cannot create a third pass.

## Protected findings and waivers

Protection is independent of severity. Findings in `security`, `correctness`, `validation`, `accessibility`, or
data-loss-protection are always non-waivable. Findings in other domains reach `waiver_required` only when explicitly
classified non-material. An accepted waiver records user identity, rationale, scope, and verification evidence in the
finding ledger and state.

## Separate replacement accounting

A design replacement and an infrastructure replacement are different events:

- `redesign_replacement_count` is zero or one for the review boundary;
- `infrastructure_replacement_count.initial` is zero or one for the initial pass; and
- `infrastructure_replacement_count.verification` is zero or one for verification.

Timeout or unavailable infrastructure requires and preserves validated partial evidence before entering the matching
incomplete state. The controller may explicitly authorize one same-pass replacement; it never retries automatically. A
second same-pass failure, declined retry, or unavailable retry becomes `redesign_required` directly. A redesign count of
one does not consume either infrastructure retry.

A terminal `redesign_required` state may enter a new design boundary exactly once with the `redesign` event. The event
requires a new `review_boundary_id`, a new reviewed commit, and a new reviewed diff digest; it may replace declared
domains/paths/requirements, clears findings and partial incomplete evidence, resets both infrastructure counters, and
returns `initial_active` with `redesign_replacement_count: 1`. The old state and source boundary remain append-only
history; the new boundary cannot infer approval from that history.

## Legacy migration

`migrate-v1` and `migrate-v2` preserve the complete legacy record under `legacy_state`. For v1, `replacement_count` maps
only to `redesign_replacement_count`; both infrastructure counters start at zero. Every migrated record is active and
non-approving under the appropriate pass, including legacy approval. Old approval is historical evidence and cannot
close a new aggregate or authorize a changed boundary or graph.

## Findings ledger and persistence

Finding records follow [`REVIEW-FINDINGS.md`](REVIEW-FINDINGS.md). The current open projection is the last record for
each finding ID with `status: open`. Resolved, accepted, and superseded records remain historical evidence.

Controllers append state before launch, after reports, before/after replacement, after redesign reconciliation, and
after verification. For feature workflows the selected review bead owns state; for standalone work the selected issue
owns it. Prompts, transcripts, assignments, and controller memory are supporting evidence, not authority.
