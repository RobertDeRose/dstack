### Goals

Keep dStack a lean, opt-in control plane for a Beads-backed feature workflow. Beads owns plans, decisions, tasks,
dependencies, gates, claims, readiness, completion, and approved project memory; Git owns repository content and
history. Provide explicit planning, review, implementation, close, and project-audit workflow commands without adding a
second workflow state machine.

### User-facing behavior

Users explicitly invoke `/plan-feature`, `/review-plan`, `/implement`, `/close-feature`, or `/audit-project`; ordinary
requests do not activate Beads tracking. Planning captures intent, review reconciles relevant repository and memory
facts, human approval exposes implementation work, and implementation handles ready tasks sequentially. Close reviews
the complete feature before documentation publication. Project audit reports current drift and, when remediation is
needed, creates only the plan step of a normal feature for later review.

Target repositories own their validation commands. Workflow commands explicitly load stage-specific skills, which are
not available for automatic model selection. Current repository documentation and accepted decisions outrank stale
memory, and memory mutation always requires explicit user approval.

### Implemented design

- `dstack init` uses idempotent Beads initialization without generic hooks or agent setup, rejects unhealthy or
  malformed
  workspace discovery, and installs the packaged feature formula and `.beads/PRIME.md`. New feature work requires the
  installed formula to match committed `HEAD` policy.
- `dstack install` installs or updates the Pi workflow commands and skills transactionally. It preflights every managed
  destination and restores replaced or stale resources if installation fails.
- Planning stores the original request in description, a directly publishable design in the Beads design field,
  observable acceptance criteria, and focused questions and answers in comments. Review searches only relevant memory
  and repository facts before creating bounded tasks with direct approval and persistent close blockers.
- Implementation tasks use concise one-line `Implementation:` notes as canonical commit material. Each fragment names
  one
  concrete delivered change and is no more than 96 characters. Task titles default to `feat(feature-slug)` and may
  select another supported Conventional Commit type with an explicit title prefix. Each repository-changing task owns
  one commit with exactly one `Task:` trailer. An unambiguous unpublished correction rewrites only that owning commit
  and
  replays descendants without folding unrelated fixups into it.
- `/close-feature` performs semantic review before claiming the close step. Reopening any implementation task blocks
  close again because each task remains a persistent ordinary blocker. Close returns owned defects to their task,
  creates one bounded task for an unowned finding, and creates directly blocking human gates only for material
  ambiguity.
- After semantic review passes, close exports the accepted design verbatim, updates the minimal feature index and
  `SUMMARY.md` entry, validates documentation separately from project checks, and uses `dstack docs commit`. New or
  changed feature documentation receives one close-owned `docs(feature-slug): feature title` commit. Valid documentation
  inherited unchanged from the base requires no new commit.
- `dstack check feature` validates all relevant feature evidence while bounding summary output. Commit paths are read
  and
  checked internally when ownership or documentation boundaries require them; there is no separate path-detail option.
- Machine output is compact deterministic JSON by default. Human inspection can request indented JSON with
  `DSTACK_OUTPUT_FORMAT=pretty`.

### Compatibility and constraints

The final Beads step keeps stable internal identity `audit` / `dstack:step:audit`, while user-facing documentation calls
it the close step. Formula version 4 replaced dynamic `waits-for` fan-in with persistent direct implementation-task
blockers. Features created with older formula versions retain their existing graph and repair a missing blocker when
review or close resumes.

Python 3.14 and Beads 1.2.2 are the tested runtime boundary. `dstack init [--update]` is the repository-policy
installation path; `dstack install` manages Pi workflow resources. Feature-level selectors use `--bead`, task-level
commands require the task issue itself, and the Beads-independent documentation check uses `--slug`. dStack does not
require target repositories to use hk or mdBook.

Formula and PRIME files are reviewed project policy. Canonical implementation and feature-documentation commits use one
`Task:` trailer and no longer require task commit-type, scope, or documentation-audience labels. Legacy `Beads:` footers
are not ownership evidence.

### Validation

Focused tests cover workspace failure handling, formula policy, plan and task validation, Beads readiness, gates,
decisions, commit creation and correction, bounded feature evidence, transactional agent-resource installation,
feature-document export, and minimal documentation structure. Real-Beads acceptance tests exercise initialization,
feature flow, claiming, persistent close blockers, worktrees, canonical commits, corrections, and feature documentation.

This repository validates with `uv run pytest`, `hk check -a`, and its release check, including installation from the
built wheel.

### Non-goals

- No dStack workflow database, readiness engine, task registry, commit map, reconciliation packet, or audit ledger.
- No automatic feature-recovery controller, memory writes, project-wide corrections, or generic Beads tracking.
- No dStack-owned target-project test command, hook dispatcher, global mdBook policy, or repository-link validator.
- No automatic semantic rewriting of exported design content, blind conflict resolution, published-history rewriting, or
  post-close fixup commits.
