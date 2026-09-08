### Goals

Make dStack a lean, opt-in control plane for the native Beads feature workflow. Beads owns plans, decisions, tasks,
dependencies, gates, claims, readiness, completion, and approved project memory; Git owns repository content and
history. Restore explicit plan, review, implement, close, and project-audit commands while minimizing repeated workflow
metadata, documentation churn, and unbounded evidence.

### User-facing behavior

Users explicitly invoke `/plan-feature`, `/review-plan`, `/implement`, `/close-feature`, or `/audit-project`; ordinary
requests do not activate Beads tracking. Planning captures intent, review reconciles relevant repository and memory
facts, human approval exposes native implementation work, and implementation claims ready tasks sequentially. Close
reviews the complete feature before publishing one feature document. Project audit reports current drift and, when
remediation is needed, creates only the plan step of a normal feature for later review.

Target repositories own their validation commands. Agent skills remain hidden from model selection behind public prompt
commands. Current repository documentation and accepted decisions outrank stale memory, and memory mutation always
requires explicit user approval.

### Implemented design

- `dstack init` uses native idempotent Beads initialization without generic hooks or agent setup, rejects unhealthy or
  malformed workspace discovery, and installs immutable packaged formula and PRIME policy. New feature work requires the
  installed formula to match committed `HEAD` policy.
- Planning stores the original request in description, this directly publishable design in the native design field,
  observable acceptance criteria in acceptance, and focused questions and answers in comments. Review searches only
  targeted memories and repository facts before creating bounded native tasks with direct approval blockers.
- Implementation tasks use concise, verb-led, one-line fragments as canonical commit material. Each fragment names one
  concrete change and is no more than 96 characters; commit formatting trims surrounding whitespace, preserves technical
  punctuation, adds `- `, and never wraps. Task titles default to `feat(feature-slug)` and may select another supported
  conventional-commit type with an explicit native title prefix. Each task owns one commit with exactly one `Task:`
  trailer; an unambiguous unpublished correction rewrites only that owning commit and replays descendants without
  autosquashing unrelated fixups. Legacy `Beads:` footers are not ownership evidence.
- `/close-feature` performs semantic review before claiming the final internal `audit` step. Every implementation task
  remains a persistent ordinary blocker of that step, so reopening a task blocks close again without rebuilding workflow
  state. Close returns defects to their owner, creates one bounded task for unowned findings, and creates directly
  blocking human gates only for material ambiguity. Changed intent updates the plan and owning task before
  implementation resumes.
- After review passes, close exports the native design verbatim, writes the minimal feature index and SUMMARY link,
  validates documentation separately from project checks, creates one close-owned `docs(feature-slug): feature title`
  commit with no body, and closes the native feature.
- Default machine output is bounded compact JSON. Human formatting uses the standard library. Beads reads are batched,
  task and feature evidence is bounded, and commit paths are opt-in.
- Skill installation preflights every destination, stages all resources, and restores replacements and stale resources
  if installation fails.

### Compatibility and constraints

This is an intentional workflow-contract change. `/audit-feature` becomes `/close-feature`; `/audit-project` returns as
an independent planning operation; the final formula step keeps its stable `audit` identity; formula version 3 removes
the fixed close-review gate from new molecules. Formula version 4 replaces `waits-for` fan-in with persistent direct
implementation-task blockers on the final step; active molecules retain the graph they were poured with and repair any
missing direct blocker when review or close resumes. Python 3.14 and Beads 1.2.2 are the tested runtime boundary.
`dstack init [--update]` is the single project-policy installation path; Bead selectors use `--bead` and standalone
documentation checks use `--slug`. dStack does not require target repositories to use hk or mdBook.

Formula and PRIME files are reviewed project policy. Canonical implementation and close documentation commits use one
`Task:` trailer and no longer require task commit-type, scope, or documentation-audience labels. Legacy `Beads:` footers
are not ownership evidence.

### Validation

Focused tests cover workspace failure handling, formula policy, lean plan and task validation, native graph readiness,
gates, decisions, commit creation and correction, bounded evidence, transactional skill installation, feature-document
export, and minimal documentation structure. Real-Beads acceptance tests exercise initialization, molecule flow,
claiming, persistent close blockers, worktrees, canonical commits, corrections, and close documentation. This repository
validates with `uv run pytest`, `hk check -a`, and its release check, including installation from the built wheel.

### Non-goals

- No dStack workflow database, readiness engine, task registry, commit map, reconciliation packet, or audit ledger.
- No automatic feature-recovery controller, memory writes, project-wide corrections, or generic Beads tracking.
- No dStack-owned target-project test command, hook dispatcher, global mdBook policy, or repository-link validator.
- No automatic semantic rewriting of exported design content, blind conflict resolution, published-history rewriting, or
  post-close fixup commits.
