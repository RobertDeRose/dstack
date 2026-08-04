# Durable review state

Review sessions are ephemeral, but review authority is durable Beads state. Every review bead—architecture, execution,
implementation, delivery, drift, or a standalone-task review—must append a machine-readable current-state record before
launching its reviewer and after every material transition.

## State record

Append one single-line JSON record to the review bead's notes with the `Review state:` prefix:

```text
Review state: {"schema":"dstack.review-state.v1","run_id":"run-...","reviewer_session_id":"session-...","packet_id":"packet-...","packet_path":"/ephemeral/...","packet_digest":"sha256:...","reviewed_commit":"<sha>","reviewed_diff_base":"<sha>","reviewed_diff_digest":"sha256:...","review_round":1,"finding_domains":["architecture"],"review_boundary_id":"boundary-...","replacement_count":0,"status":"active","disposition":"pending","replacement_reason":null,"supersedes_run_id":null,"unavailable_reason":null}
```

Required fields are:

- `schema`: exactly `dstack.review-state.v1`;
- `run_id`: immutable identifier for this review run;
- `reviewer_session_id`: identifier supplied by the reviewer harness;
- `packet_id`, `packet_path`, and `packet_digest`: packet identity, ephemeral location, and content digest;
- `reviewed_commit`, `reviewed_diff_base`, and `reviewed_diff_digest`: exact reviewed source boundary;
- `review_round`: positive integer for the current review/reconciliation round;
- `finding_domains`: stable lower-case domain identifiers for the current findings;
- `review_boundary_id`: immutable identifier for the current design/specification boundary;
- `replacement_count`: zero or one for a bounded redesign replacement within that boundary;
- `status`: `active`, `findings`, `verified`, `unavailable`, `replaced`, or `redesign_required`;
- `disposition`: `pending`, `changes_required`, `approved`, `replaced`, or `redesign_required`;
- `replacement_reason`, `supersedes_run_id`, and `unavailable_reason`: explicit values when applicable, otherwise
  `null`.

The last `Review state:` line is the canonical current state. Earlier records remain append-only audit history and must
not be interpreted as current findings or approval. A later state for the same `run_id` resumes the original reviewer
against a new reviewed commit or diff boundary.

## Convergence threshold

A review round is one review run followed by its reconciliation and verification attempt. The controller must preserve
stable domain identifiers in `finding_domains`; do not compare free-form prose or reviewer wording. An unresolved
material finding is a finding whose current disposition remains `changes_required` after the round. Before launching
another role reviewer, inspect the current state and ledger:

- If two unresolved review rounds in the same domain are consecutive, append `status: redesign_required` and
  `disposition: redesign_required` to the affected review bead(s), preserving the domain and round numbers.
- Do not launch another reviewer while the threshold is active. Keep or reopen `spec-reconcile` and route the feature to
  the design-question or decomposition phase; do not silently patch the same boundary again.
- After a new design/decomposition boundary is committed, start a new packet and review round. The prior run remains
  audit history and does not carry approval into the redesigned boundary.
- Findings in unrelated domains, or a resolved round between two findings, do not trigger this threshold.

## Bounded redesign replacement

A material scope change invalidates the whole review run, not just one role's interpretation. Do not launch a fresh
replacement reviewer in the same run. Append `status: replaced`, `disposition: replaced`, and a concrete
`replacement_reason`, keep the original packet and findings as audit history, and reopen `spec-reconcile`.

After the redesigned boundary is committed, rebuild one redesigned packet and run one new four-role review. Give the new
run a new `review_boundary_id`, `supersedes_run_id` pointing to the invalidated run, and `replacement_count: 1`. No
second redesign replacement is allowed within that boundary; foundational findings in the new run enter the convergence
threshold above. A reviewer that is unavailable without a scope change follows the ordinary replacement path and does
not consume the redesign replacement allowance.

## Required lifecycle

1. Claim the review bead and append an `active` record before launching the reviewer.
2. Capture the exact packet identity and source boundary before the reviewer reads it. A packet path may be ephemeral,
   but its ID and digest must remain durable.
3. Append `findings` with the current disposition and verification boundary after review. Append `verified` only after
   actionable findings are resolved and the affected checks pass.
4. After a fix, resume the original `run_id`; append its new reviewed commit/diff boundary rather than creating a fresh
   run. Do not relaunch a reviewer merely because the controller lost conversational context.
5. If the original reviewer cannot be resumed, append `unavailable` with a concrete reason before launching a
   replacement. Create a new run with `supersedes_run_id`, pass the prior packet identity, findings ledger, resolutions,
   and post-review diff to the replacement, and record the replacement reason on both review beads.
6. A replacement must not erase the original record or silently reuse its approval. The controller closes the review
   bead only after its canonical state is `verified` or an explicitly recorded terminal disposition.

Use Beads notes for the durable record; do not store the authoritative state only in an ephemeral packet, transcript, or
controller memory. The replacement reviewer receives the prior findings ledger and resolutions as input. Finding IDs and
current dispositions follow [`REVIEW-FINDINGS.md`](REVIEW-FINDINGS.md).
