# Review loop

Reviewers provide independent evidence. They do not own workflow authority.

## Authorized passes

Invoking a review-capable dstack command authorizes:

1. one initial independent review;
2. correction of actionable in-scope findings;
3. one verification review against the corrected committed candidate.

When another review is warranted after the verification review, explain the new
finding and correction, then ask the user whether to run another independent
review. Explicit permission always permits it. There is no maximum pass count
and no convergence state that can override the user.

## Outcomes

Use these meanings consistently without building a new state machine:

- **changes requested**: an implementation, documentation, test, security,
  performance, or maintainability defect can be corrected inside accepted scope;
- **decision required**: accepted product or architecture intent must change or
  repository evidence cannot determine the intended behavior;
- **validation pending**: required evidence must run in another environment or at
  a later stage;
- **review unavailable**: the reviewer could not run or return usable evidence;
- **approved**: no unresolved material findings remain for this boundary;
- **accepted risk**: the user explicitly accepts a documented unresolved risk
  and repository policy permits proceeding.

A new defect or missing assertion is not redesign. Reviewer infrastructure
failure is not a design result.

## Boundaries

Review a committed Git candidate. Any correction creates a new candidate commit
or safely amends an unpublished private task commit. Do not claim approval for
uncommitted or moving source.

Reviewers are read-only. They inspect the accepted design, selected Bead,
candidate diff, relevant source/tests/docs, and validation evidence. They do not
edit source or mutate Beads.

## Durable record

After each completed review boundary, add one concise Markdown comment from a
temporary file:

```bash
bd comments add <task-id> -f <review-summary.md>
```

Record only durable evidence:

- reviewed commit;
- validation performed;
- material findings;
- corrections and resulting commit;
- final outcome;
- pending external validation or accepted risk.

Do not persist model transcripts, hidden reasoning, pass counters, or reviewer
replacement topology.
