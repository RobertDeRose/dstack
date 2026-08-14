# Review findings ledger

Review notes are append-only. Every feature review bead, or selected standalone task, stores finding records with the
`Finding:` prefix. Group records by immutable `finding_id`; the last record is current and earlier records remain audit
history.

## Finding record

```text
Finding: {"schema":"dstack.review-finding.v1","finding_id":"F-001","domain":"architecture","severity":"blocking","material":true,"protected":false,"status":"open","source_boundary":{"review_issue_id":"dstack-mol-2s9-clarity","reviewer_session_id":"session-...","reviewed_commit":"<sha>","reviewed_diff_base":"<sha>","reviewed_diff_digest":"sha256:..."},"summary":"...","resolution":null,"verification":null,"waiver":null,"supersedes_finding_id":null}
```

Required fields are:

- `schema`: exactly `dstack.review-finding.v1`;
- `finding_id`: immutable within the review record;
- `domain`: stable lowercase kebab-case identifier; domains are open-ended, while only the protected set has special
  waiver semantics;
- `severity`: `blocking`, `high`, `medium`, or `low`;
- `material`: explicit boolean used by verification state;
- `protected`: true for security, correctness, validation, accessibility, and data-loss-protection findings regardless
  of severity;
- `status`: `open`, `resolved`, `superseded`, or `accepted`;
- `source_boundary`: owning Beads review issue, reviewer session, reviewed commit/base, and diff digest;
- `summary`: concise statement retained across updates;
- `resolution` and `verification`: null while open, otherwise concrete evidence;
- `waiver`: null unless accepted, then user identity, rationale, scope, and verification evidence; and
- `supersedes_finding_id`: prior ID only when this finding intentionally replaces another.

Resolved and accepted records require non-null resolution and verification. Accepted records additionally require an
eligible non-material, non-protected finding and complete waiver evidence. Protected findings can never be accepted.
Superseded records name their replacement. Never reuse an ID for a different issue or rewrite prior records.

## Current-state projection

Parse every `Finding:` line, group by `finding_id`, and retain the last record. Include only current `status: open`
records in the active reviewer assignment. Keep resolved, accepted, and superseded records in historical audit evidence,
but do not present them as current recommendations.

A replacement reviewer receives the same source boundary and open findings/resolutions needed for handoff. The ledger
remains Beads authority; prompts, assignments, and transcripts are not substitutes. Aggregate review state uses current
material/protected classifications rather than severity or free-form prose to determine redesign and waiver eligibility.
