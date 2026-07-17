# Design — Migration safety and clarity

## Metadata

- Beads feature root: `dstack-mol-tki`
- Feature slug: `migration-safety-and-clarity`
- Design path: `docs/src/features/migration-safety-and-clarity/design.md`
- Implemented record: `docs/src/features/migration-safety-and-clarity/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Make `/migrate-workflow` preserve existing hk behavior by default, clearly explain every requested decision, classify
migration artifacts, and require verified checkpoint commits.

## User Intent

Migration should add dstack workflow capability without deleting working project checks. Questions must provide enough
context and examples for informed answers. Archived legacy tasks should have an explicit lifecycle. Agents must never
hide migration failures with `git commit --no-verify`.

## Goals

- Preserve every existing hk step unless the user explicitly approves and records its removal.
- Detect step collisions and pre/post capability loss before migration completion.
- Clearly distinguish durable committed archives, temporary candidates, and conditional backups.
- Give each migration question purpose, evidence, impact, examples, choices, safe default, and deferral consequence.
- Prohibit broad hook bypasses and stop with actionable recovery when a hook fails.
- Exercise these guarantees in one resumable end-to-end migration fixture.

## Non-Goals

- Parse or rewrite arbitrary Pkl syntax automatically.
- Guarantee semantic equivalence for an hk config that cannot be evaluated in its original repository.
- Delete historical task archives by default.
- Infer project purpose, users, scope, boundaries, classifications, or collision resolutions.
- Weaken repository hooks or documentation policy to make intermediate migration checkpoints pass.

## User-Facing Behavior

Before adoption changes hk, migration records the existing hook and step inventory and a non-destructive readiness
result when evaluable. Generated hk is an additive candidate. Existing keys remain authoritative until the user resolves
a collision with an explanation of both behaviors. Verification rejects unapproved step loss.

`migration/legacy-tasks/*.md` is reported as durable audit evidence that must be tracked and committed by default.
Candidate directories are temporary and must be removed. Every prompt explains why it is being asked, shows a concrete
answer, and states what happens when the user defers.

Migration uses ordinary verified commits. A hook failure stops the checkpoint and reports the failing hook, the relevant
migration-safe validation command, and recovery. It never uses or recommends `--no-verify`.

## Requirements

### Functional Requirements

#### Additive hk reconciliation

Before template adoption, record the evaluable hook/step inventory by hook name and step key. After candidate
reconciliation, compare the final inventory. Existing steps must remain unless a durable migration decision records:

- the removed or replaced key;
- existing and candidate behavior;
- the user's explicit disposition;
- the reason removal or replacement is safe.

A same-key collision is not silently resolved in favor of dstack. The workflow presents both definitions and asks one
contextual question. If the original config cannot be evaluated, migration reports that limitation and requires manual
inventory confirmation; it does not assume the generated policy supersedes it.

The adoption helper may continue staging `hk.pkl` as a candidate rather than implementing a general Pkl merge. The
migration workflow and verifier own the preservation guard. An unchanged repeated scan preserves the prior timestamp and
committed report bytes; volatile generation time changes only when semantic scan state changes.

#### Artifact lifecycle

Migration reports classify paths as:

| Class                       | Examples                                                                             | Completion contract                                               |
|-----------------------------|--------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| Durable audit state         | `migration/workflow-migration.json`, report, baseline, `migration/legacy-tasks/*.md` | Tracked and committed                                             |
| Temporary reconciliation    | `migration/template-adoption-candidates/`                                            | Removed before checkpoint                                         |
| Conditional backup evidence | `migration/template-adoption-backup/`                                                | Retained or removed according to an explicit recorded disposition |

Default finalization archives legacy `tasks.md` into `migration/legacy-tasks/<slug>.md`. `--delete-tasks` remains an
explicit alternative when Git history is accepted as sufficient. The manifest records backup disposition as
`unresolved`, `retain`, or `remove`, defaulting older manifests to `unresolved`; verification rejects a present backup
or recorded removal without a resolved disposition. Verification also rejects untracked durable migration artifacts and
leftover temporary candidates.

#### Contextual question contract

Each migration question contains:

1. a concise decision title;
2. why migration needs the answer now;
3. current authoritative evidence and uncertainty;
4. the behavior or files the answer controls;
5. one valid concrete example;
6. available choices and a safe default when one exists;
7. the consequence of deferring.

This contract applies to structured brief fields, project kind, feature classification, missing design intent,
dependency direction/type, hk collisions/removals, candidate file reconciliation, archive deletion, and other explicit
policy choices. Questions remain one at a time. The skill and reference own one reusable checklist and representative
examples rather than a new prompt-rendering framework. Durable state stores only answers needed for safety or
resumability, not copies of conversational prose.

#### Verified checkpoint commits

Migration instructions and helpers never use or recommend `git commit --no-verify`. Gate 2 first captures legacy
inventory/readiness, completes candidate reconciliation, and reaches a clean conflict gate. Only then may it invoke the
existing generated project-local `scripts/setup-tooling.py --json`; no second installer is introduced. Lock, install,
and hook setup must succeed or stop with the provisioner's recovery commands. Migration verifies the installed Git hook
routing and direct config readiness before the adoption commit, so the ordinary commit exercises the reconciled pinned
hook rather than ambient tooling.

If strict final documentation is intentionally premature because legacy task files remain, the only supported targeted
exception is explicit user-approved `HK_SKIP_STEPS=docs git commit ...` after
`uv run scripts/check-docs.py --migration-mode` passes. The durable migration note records approval, reason, equivalent
result, and residual risk; every other configured hook step still runs. Once finalization removes legacy inputs,
ordinary commits run strict docs without that environment variable. A hook failure stops, names the hook/step, preserves
the worktree, and gives a reproduction and recovery command. `HK_SKIP_HOOK` and broad bypass remain prohibited.

### Quality Requirements

- Preservation checks compare behavior inventories, not raw formatting.
- Repeated scans/import/finalization remain idempotent, including byte-stable durable scan/report output when inputs are
  unchanged.
- Prompt contract tests cover every decision category.
- Failure fixtures prove unapproved step loss, untracked archives, temporary leftovers, and hook failure block
  completion.
- Final migration leaves strict docs, tests, Beads graph, hooks, and worktree clean.

### Compatibility and Migration Requirements

Existing migration manifests remain readable. New inventory, artifact, answer, and checkpoint evidence uses optional
schema fields with explicit defaults; missing inventory/readiness and unresolved backup disposition block mutation until
captured or decided. Resuming an older migration captures baseline evidence before further mutation, preserves imported
Beads identities, and preserves existing archived tasks.

## Existing Context

The adoption helper preserves differing project-owned files and stages generated candidates, but manual reconciliation
can still remove existing hk steps. Current guidance says to preserve project-specific content generally without an hk
capability-loss guard. The reference already defines `migration/legacy-tasks` as the default archive, yet completion
language does not make an untracked archive's invalid state prominent. Questions name required fields but do not provide
a consistent context/example contract. The skill's command examples do not contain `--no-verify`, but they do not
explicitly prohibit it or prove hooks ran.

## Proposed Design

Extend migration state with pre/post hk inventories and explicit dispositions, add artifact classification and tracked
state checks, standardize contextual question templates, and strengthen checkpoint gates around real hook execution.
Keep candidate reconciliation manual where syntax-aware merging would be unsafe. Validate the complete behavior in a
legacy repository fixture containing custom hk steps and a deliberately failing hook.

## Architecture Consistency

### Existing Patterns Reused

The feature reuses dry-run gates, resumable manifests, explicit user decisions, candidate staging, migration-mode docs
validation, strict final verification, and durable evidence records.

### Invariants Preserved

Legacy text remains untrusted evidence; Copier does not overwrite project-owned files; semantic decisions require the
user; migration is resumable; Beads becomes live work authority only after verified import; final worktree is clean.

### New Decisions Introduced

Existing hk behavior is protected by an explicit capability inventory. Migration artifacts have normative lifecycle
classes. Broad hook bypass is prohibited, and prompt clarity has a testable minimum contract.

### Architecture Documentation Changes

`docs/src/architecture/index.md` will document additive adoption and the hook-verification boundary.

## Operational Considerations

An unevaluable legacy hk config may require manual inventory confirmation and can delay migration. This is preferable to
silent loss. Hook failures may expose pre-existing defects; baseline readiness evidence aids attribution without proving
it. Recovery remains local and resumable. Durable archives increase repository size slightly but preserve evidence.

## Documentation Impact

| Documentation concern      | Exact page                                                | Create or update        | Planned change                                                                                                        | Owning Beads task                |
|----------------------------|-----------------------------------------------------------|-------------------------|-----------------------------------------------------------------------------------------------------------------------|----------------------------------|
| Architecture               | `docs/src/architecture/index.md`                          | Update                  | Additive adoption and hook-verification boundary                                                                      | `dstack-mol-9zl.5`               |
| Usage / Operations         | `docs/src/operations/index.md`                            | Update incrementally    | Questions/collisions (`.1`, `.3`), artifact lifecycle (`.2`), verified checkpoints, failure/exception recovery (`.4`) | tasks `.1`–`.4`; `.5` reconciles |
| Development                | `docs/src/development/index.md`                           | Update incrementally    | Checkpoint validation and contributor workflow (`.4`), combined fixtures (`.5`)                                       | tasks `.4`–`.5`                  |
| Reference                  | `docs/src/reference/index.md`                             | Update incrementally    | Exact commands/defaults plus inventory (`.1`), artifact (`.2`), answer (`.3`), and checkpoint (`.4`) fields           | tasks `.1`–`.4`; `.5` reconciles |
| Skill procedure            | `skills/migrate-workflow/SKILL.md`                        | Update                  | Ordered gates, contextual questions, verified commits                                                                 | tasks `.1`–`.4`                  |
| Migration reference        | `skills/migrate-workflow/references/MIGRATION.md`         | Update                  | Detailed reconciliation, archive, and recovery procedures                                                             | tasks `.1`–`.4`                  |
| Navigation                 | `docs/src/SUMMARY.md`                                     | Update design markers   | Register this design                                                                                                  | planning                         |
| Implemented Feature Record | `docs/src/features/migration-safety-and-clarity/index.md` | Create during close-out | Preserve delivery and audit history                                                                                   | lifecycle close-out              |

## Validation Strategy

- Preserve and compare custom hk steps in a legacy migration fixture.
- Inject same-key collisions and require a recorded disposition.
- Reject unapproved step deletion and unevaluated claims of equivalence; require manual confirmation for unevaluable hk.
- Repeat unchanged `scan --write` and assert byte-stable manifest/report output.
- Finalize into tracked archives; reject untracked archives, candidate leftovers, and unresolved backup disposition;
  cover retained and removed backups.
- Assert every named prompt category includes the seven required context elements without snapshotting incidental prose.
- Use failing and successful provisioner/hook fixtures to prove checkpoint mutation stops or commits through installed
  hooks; cover the targeted docs exception record.
- Resume an older manifest before mutation; preserve baseline evidence, imported Beads identities, and existing
  archives.
- Resume after each failure and confirm idempotence.
- Run migration verifier with Beads, strict documentation checks, focused/full tests, and final clean status.

## Implementation Decomposition

1. `dstack-mol-9zl.1`: capture inventories/readiness, preserve byte-stable scans, guard additive hk reconciliation, and
   update its operations/reference sections.
2. `dstack-mol-9zl.2`: classify artifacts, enforce backup disposition and durable tracking, and update its
   operations/reference sections.
3. `dstack-mol-9zl.3`: standardize the reusable contextual-question checklist/examples and update its
   operations/reference sections.
4. `dstack-mol-9zl.4`: provision the reconciled pinned hook, prohibit broad bypass, validate checkpoint hooks/targeted
   exceptions, and update development/operations/reference sections.
5. `dstack-mol-9zl.5`: exercise old-manifest compatibility and the complete resumable migration, then reconcile all
   reader documentation.

## Dependencies and Parallelism

This feature depends on hk policy simplification so its candidate inventory reflects the final generated policy. Tasks
are serialized because they share the migration skill, reference, script, manifest, and integration fixture. Every task
depends directly on specification reconciliation. Each task runs its named focused migration test with
`uv run --frozen --group test pytest`, `uv run scripts/check-docs.py`, `HK_JOBS=1 mise run check`, and the full
`uv run --frozen --group test pytest` suite before commit; `.5` additionally runs the complete migration test partition
and asserts final clean status.

## Rollout and Migration

Apply the stronger checks to new and resumed migrations. Older manifests first capture missing inventories and artifact
state without changing imported Beads identities. A migration blocked by new evidence requirements remains resumable.

## Risks and Tradeoffs

Capability inventories cannot prove semantic equivalence for arbitrary custom shell commands, so collisions remain a
human decision. More contextual prompts make individual questions longer but reduce uninformed answers and rework.
Strict hook enforcement may uncover legacy defects earlier and lengthen migration, which is the intended safety
tradeoff. Pre-adoption readiness evidence supports attribution but cannot by itself prove whether every later failure
was pre-existing.

## Rejected Alternatives

- Automatically replace existing `hk.pkl`: rejected because it can delete important checks.
- General Pkl AST merging: rejected as disproportionate and unsafe for arbitrary expressions/imports.
- Treat untracked archives as optional local evidence: rejected because completion requires a clean durable record.
- Keep terse questions: rejected because the user cannot judge scope or consequences.
- Permit `--no-verify` for intermediate commits: rejected because it bypasses unrelated safeguards.

## Open Questions

None.

## Deferred Decisions

No native implementation decision is deferred. Broader Copier merge automation requires a separate demonstrated need.

## Planning Record

### Questions Asked and Answers

The user reported lost hk steps, unclear migration questions, an untracked legacy task archive, and commits made with
`--no-verify`. They expect additive behavior, contextual explanations, durable records, and verified commits.

### Assumptions

Legacy repositories may contain arbitrary valid hk/Pkl configuration and project-specific hooks. Git is available
because migration already requires a repository and clean checkpoint boundaries.

### Design Changes During Planning

The plan separates template hk simplification from migration protection, keeps Pkl reconciliation manual, and adds an
automated capability-loss guard rather than attempting syntax-aware merging.

### Source Material

Current migration skill, reference, adoption and migration scripts, migration fixture tests, generated hk policy, and
the user's completed migration observations.
