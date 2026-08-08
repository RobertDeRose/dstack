# Review findings ledger

Review notes are append-only, but a reviewer or context builder must not treat historical prose as current state. Each
feature review bead, or the selected standalone task record, stores finding records with the `Finding:` prefix. The last
record for a `finding_id` is its canonical current disposition; earlier records remain audit history.

## Finding record

Append one single-line JSON record for each finding:

```text
Finding: {"schema":"dstack.review-finding.v1","finding_id":"F-001","domain":"architecture","severity":"blocking","status":"open","source_boundary":{"packet_digest":"sha256:...","reviewer_session_id":"session-...","reviewed_commit":"<sha>","reviewed_diff_digest":"sha256:..."},"summary":"...","resolution":null,"verification":null,"supersedes_finding_id":null}
```

Required fields are:

- `schema`: exactly `dstack.review-finding.v1`;
- `finding_id`: immutable within the review record and reused when its disposition changes;
- `domain`: stable lower-case domain identifier used by the convergence threshold;
- `severity`: `blocking`, `high`, `medium`, or `low`;
- `status`: `open`, `resolved`, `superseded`, or `accepted`;
- `source_boundary`: packet digest, reviewer session, reviewed commit, and diff digest that produced the finding;
- `summary`: concise finding statement, retained when later records update the disposition;
- `resolution`: current resolution text, or `null` while unresolved;
- `verification`: command/result/commit evidence, or `null` while unresolved;
- `supersedes_finding_id`: the prior finding ID when this record intentionally replaces another finding, otherwise
  `null`.

A `resolved` or `accepted` record must include a non-null resolution and verification. A `superseded` record must name
the replacement finding. Do not reuse an ID for a different issue or silently rewrite an earlier record.

## Current-state projection

To build active review context, parse all `Finding:` records, group by `finding_id`, and retain only the last record for
each ID. Include only currently open findings in the active summary. Preserve resolved, accepted, and superseded records
in the historical audit section, but do not present them as unresolved findings or recommendations. For standalone work,
perform this projection from the selected task's notes; no separate review bead is authoritative.

The context builder passes the current open projection, the packet/source boundary that produced it, and the relevant
historical resolutions to reviewers. A replacement reviewer receives the same projection plus the complete prior
findings and resolutions needed to understand supersession. The ledger is Beads note state; an ephemeral packet or
controller memory is not an authoritative substitute.
