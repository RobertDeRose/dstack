# dStack Engineering Quality Contract

## Goal

Give every dStack feature a small, reusable quality contract before implementation so the resulting behavior is
well-designed, behaviorally tested, and documented for the people and agents who must use or maintain it. The contract
must improve engineering judgment without adding workflow state or approval bureaucracy.

## User-visible behavior

Feature authors get a design structure that makes the following explicit:

- the user or developer outcome being added;
- behavior that is deliberately out of scope;
- existing patterns or components being reused;
- why any new abstraction is necessary;
- observable success behavior;
- failure, negative, security, and compatibility behavior;
- the validation strategy; and
- the documentation surfaces affected.

`dstackctl feature scaffold-design <feature>` creates the minimal design scaffold when the feature design does not
exist. The scaffold contains these sections:

- Goal
- User-visible behavior
- Non-goals
- Existing patterns and reuse
- Design
- Failure / security / compatibility behavior
- Validation strategy
- Documentation impact

Running the command again leaves an existing design byte-for-byte unchanged. A missing parent directory is created only
as needed.

`feature add-task` and `alignment add-correction` reject missing or whitespace-only acceptance criteria before creating
a Bead. They check only presence; the agent judges whether the stated outcome is meaningful. Acceptance criteria
describe observable outcomes, including relevant tests and documentation, rather than implementation names.

Tests prove externally meaningful behavior, invariants, failure handling, and regression boundaries. They should fail
when behavior is wrong, not merely prove that the current implementation was executed. Specification review explicitly
examines happy-path outcomes, invalid-input rejection, state-transition or persistence behavior, failure recovery,
security boundaries where relevant, and compatibility or regression behavior. It discourages private-method coverage
probes, implementation-structure assertions, and mocks that prevent the real behavior from occurring. No
coverage-percentage gate is introduced.

## Non-goals

- scoring systems, design grades, approval matrices, or additional Beads metadata;
- semantic or AI classification of acceptance criteria;
- a separate documentation set for future agents;
- separate test-only or documentation-only tasks when they are part of one behavioral outcome; and
- persistent active-feature state, caches, ledgers, or other workflow bookkeeping.

## Existing patterns and reuse

The change reuses the existing Markdown skill and documentation structure, the single `dstackctl.py` argparse entry
point, current feature resolution and root metadata, the existing Beads client, and the current pytest contract and
controller test helpers. The command is necessary because agents currently recreate the same deterministic scaffold
manually; it is not a reason to add a new abstraction layer. Existing task text handling and native Beads creation
remain the source of truth for task input.

## Design

The quality contract is durable guidance in `docs/src/development/index.md` and the feature lifecycle skills. The
start-feature guidance points authors at the scaffold and quality questions. Specification review, implementation, and
closeout guidance share the behavioral-testing principle and the documentation impact check.

The scaffold command resolves the selected current feature, reads its existing repository-relative design path, and
writes a fixed template only when the file is absent. It returns the resolved path and whether a file was created. An
existing file is never merged, normalized, or overwritten. The command derives all context from Beads and Git during the
invocation and persists nothing beyond the design file itself.

The task-creation guards apply after reading either inline or file-based acceptance text and before any native Beads
create operation. They use the existing task-text normalization for presence checking and preserve the current
meaningful-input behavior sent to Beads. No semantic acceptance parser is added.

## Failure / security / compatibility behavior

- A missing feature, missing design path, or invalid repository-relative path fails without creating a file or Bead.
- Absolute paths, parent traversal, and symlink escapes outside the selected repository are rejected before scaffold
  writes.
- Existing design content is never changed by scaffold retries, protecting in-progress authoring from data loss.
- Empty acceptance input fails before Beads mutation; valid existing commands retain their current JSON shape and native
  dependency behavior.
- The command is safe to retry after an interrupted invocation because creation is conditional and idempotent.
- The quality contract does not change Beads readiness, ownership, or lifecycle semantics.

## Validation strategy

Behavior-focused tests will verify the observable scaffold creation and non-overwrite behavior, invalid design-path
rejection, blank and whitespace acceptance rejection for both task-creation commands, and successful creation with an
outcome-oriented criterion. Documentation contract tests will assert the shared testing principle, quality questions,
and audience table remain present. The tests will use the existing fake only for command-boundary injection and argument
checks; no new Beads lifecycle model will be added. The existing repository suite remains the final compatibility check.

## Documentation impact

| Perspective | Question and outcome |
| --- | --- |
| End user/operator | The command help and design guidance explain how to create a safe feature design and what observable behavior and documentation to provide. |
| Developer/reviewer | Core principles and lifecycle skills define the quality questions, behavioral-test expectations, and review boundaries used to assess the feature. |
| Future agent/auditor | The same durable principles, scaffold headings, contract tests, and feature design establish intent strongly enough to detect drift; no separate agent documentation is needed. |
