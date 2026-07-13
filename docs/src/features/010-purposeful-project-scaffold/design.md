# Design — F010 Purposeful project scaffold

## Metadata

- Beads feature root: `dstack-mol-ln9`
- Feature number: `010`
- Feature slug: `purposeful-project-scaffold`
- Design path: `docs/src/features/010-purposeful-project-scaffold/design.md`
- Implemented record: `docs/src/features/010-purposeful-project-scaffold/index.md`
- Base branch: `main`
- Status: reviewed

## Feature Summary

Make `/setup-project` collect a concrete project brief and kind, then render a small truthful mdBook without empty
section indexes or replacement-style prose.

## User Intent

dstack should dog-food its documentation-first workflow. New projects should begin with truthful documentation rather
than prose telling maintainers what to write later.

## Goals

- Require purpose, intended users, current scope, key boundaries, and project kind for new setup.
- Support project kinds: library, CLI, service, application, infrastructure, documentation, and other.
- Render known facts into README, book metadata, project overview, roadmap, and documentation conventions.
- Omit architecture, usage, development-overview, and reference-overview pages until concrete content exists.
- Record stable deterministic Copier answers.

## Non-Goals

- Generate application source code, package manifests, framework architecture, usage commands, deployment facts, or API
  contracts.
- Infer unconfirmed project facts from a name or kind.
- Preserve pre-1.0 setup, migration, adoption, or Copier update compatibility.
- Change setup/update/migration authority or overwrite boundaries.
- Make implementation-language decisions; F030 owns language profiles.

## User-Facing Behavior

The setup skill asks for each missing brief field one question at a time, then asks the user to select the project kind.
It invokes the helper with explicit flags and does not add a redundant confirmation question. Direct helper invocation
requires the same fields. Every kind receives the same minimal factual reader pages; project kind changes only the
applicable-future-concerns guidance in documentation conventions.

## Requirements

### Functional Requirements

#### Canonical input contract

| Copier answer        | Helper flag      | Type | Validation                      | Rendered ownership                                                           |
|----------------------|------------------|------|---------------------------------|------------------------------------------------------------------------------|
| `project_purpose`    | `--purpose`      | str  | Trimmed, non-empty, single line | README summary, `book.toml` description, overview Purpose, roadmap direction |
| `project_users`      | `--users`        | str  | Trimmed, non-empty, single line | Overview Intended users                                                      |
| `project_scope`      | `--scope`        | str  | Trimmed, non-empty, single line | Overview Current scope, roadmap direction                                    |
| `project_boundaries` | `--boundaries`   | str  | Trimmed, non-empty, single line | Overview Boundaries, roadmap direction                                       |
| `project_kind`       | `--project-kind` | enum | Exact lowercase choice          | Overview project kind and documentation-concern guidance                     |

Accepted kind values are `library`, `cli`, `service`, `application`, `infrastructure`, `documentation`, and `other`. The
helper rejects NUL, CR, and LF in brief fields and reports the missing/invalid flag and accepted kinds. Unicode, quotes,
apostrophes, backslashes, Markdown punctuation, and TOML-sensitive characters remain valid. `book.toml` uses TOML-safe
string serialization rather than raw quoted interpolation.

Both Copier entrypoints define the same answers. `project_description` is removed. The helper validates and forwards all
fields to Copier with `unsafe=False` and `overwrite=False`; the installed skill documents the same question sequence and
flags.

#### Universal rendered reader files

All seven kinds render the same minimal reader set because the approved brief contains no truthful architecture, usage,
development-toolchain, configuration, deployment, or API facts:

| Path                                                 | Content source                                             |
|------------------------------------------------------|------------------------------------------------------------|
| `README.md` when enabled                             | Project name, purpose, and dstack workflow entry points    |
| `docs/book.toml`                                     | Project name and TOML-safe purpose                         |
| `docs/src/SUMMARY.md`                                | Only the useful universal pages listed below               |
| `docs/src/introduction/project-overview.md`          | Kind, purpose, users, current scope, and boundaries        |
| `docs/src/introduction/documentation-conventions.md` | Source ownership plus kind-specific future concerns        |
| `docs/src/development/feature-lifecycle.md`          | dstack workflow contract                                   |
| `docs/src/planned-features.md`                       | Brief-derived project direction and truthful empty roadmap |
| `docs/src/features/index.md`                         | Truthful empty implemented-feature state                   |

`docs/src/index.md`, `architecture/index.md`, `operations/index.md`, `development/index.md`, and `reference/index.md`
are not rendered. `SUMMARY.md` links the overview as the book landing page, then documentation conventions, feature
lifecycle, planned features, and implemented features.

Internal authoring templates under `docs/src/features/_template/` remain universal and intentionally contain literal
prompts/tokens; they are not reader-facing chapters.

#### Kind-specific future concerns

Project kind does not fabricate pages. It selects concise guidance in `documentation-conventions.md` for pages to add
when implementation supplies facts:

| Kind             | Applicable future concerns                                                                                                   |
|------------------|------------------------------------------------------------------------------------------------------------------------------|
| `library`        | installation/usage, public API and compatibility reference, diagnostics, development, architecture decisions                 |
| `cli`            | installation/usage, commands/configuration/files/exit behavior, troubleshooting, development, architecture decisions         |
| `service`        | deployment/operations/health/observability/recovery, interfaces/configuration, development, architecture/security boundaries |
| `application`    | getting started and user workflows, configuration/troubleshooting, development, architecture decisions                       |
| `infrastructure` | environments/deployment/operations/recovery, inventory/configuration/security reference, development, architecture decisions |
| `documentation`  | authoring/development, structure/style/publication reference                                                                 |
| `other`          | no concern is presumed; add a page only when a durable reader question exists                                                |

#### Documentation validation

Both `scripts/check-docs.py` and `skills/setup-project/template/scripts/check-docs.py` stop requiring a fixed taxonomy.
They continue validating every present local link, feature-directory contract, design/implemented headings, internal
design/task navigation prohibitions, implemented-feature markers, and delivered-record registration. They do not need to
parse Copier answers or project kind because absent pages are valid for every kind.

- No generated reader page may contain unresolved replacement instructions asking the project owner to supply project
  facts.
- Workflow guidance in documentation conventions, feature lifecycle, and internal feature templates is allowed.
- `planned-features.md` must contain brief-derived direction and truthful empty states rather than “summarize” or
  “record” prompts.

### Quality Requirements

- Setup safety, bundled-template authority, source recording, `unsafe=False`, and no-overwrite behavior remain intact.
- Every kind render passes the generated checker and mdBook build.
- Both Copier entrypoints remain aligned and conditional destinations do not collide.
- Tests cover quotes, backslashes, Unicode, Markdown punctuation, rejected control characters, and whitespace-only
  values.

### Compatibility and Migration Requirements

This is intentionally breaking pre-1.0 work. F010 guarantees new setup only. Updating or adopting a pre-F010 generated
project is not supported by this feature and must not fabricate missing brief values. Migration and update workflows
retain their existing trust and overwrite boundaries but may reject old answer sets. Compatibility policy will be
established before v1.

## Existing Context

The current template accepts one generic description, emits fixed section indexes containing authoring prompts, and
requires all documentation concerns in `SUMMARY.md`. dstack now dog-foods a concrete mdBook and shared docs validation.

## Proposed Design

Replace `project_description` with the five canonical answers and flags. Render one small shared book backed only by
those facts. Use project kind only to tailor future-concern guidance. Delete redundant and empty section landing pages.
Remove the checker's mandatory taxonomy loop without weakening validation of files that exist.

## Architecture Consistency

### Existing Patterns Reused

Copier answer parity, explicit helper forwarding, bundled-template authority, strict destination checks, and the
stdlib-only documentation checker.

### Invariants Preserved

Setup remains new-project-only, deterministic, non-overwriting, and offline with respect to template source. Skills CLI
owns installed skills, Copier owns generated scaffold state, and Beads owns executable work.

### New Decisions Introduced

Project kind is recorded context, not permission to invent product documentation. Initial generated reader files are
identical across kinds; only workflow guidance differs.

### Architecture Documentation Changes

`dstack-mol-a8i.2` updates `docs/src/architecture/index.md` with the input-to-template rendering boundary.

## Operational Considerations

Direct invocation becomes intentionally stricter. Missing and invalid input errors name the exact flag. Existing
non-empty destination, managed-project, Git, Beads, and docs-validation behavior remains unchanged.

## Documentation Impact

| Documentation concern      | Exact page                                                   | Create or update                     | Planned change                                                 | Owning Beads task  |
|----------------------------|--------------------------------------------------------------|--------------------------------------|----------------------------------------------------------------|--------------------|
| Introduction               | `docs/src/introduction/project-overview.md`                  | Update                               | Document structured brief and minimal output                   | `dstack-mol-a8i.2` |
| Architecture               | `docs/src/architecture/index.md`                             | Update                               | Document kind-as-context rendering boundary                    | `dstack-mol-a8i.2` |
| Usage                      | `docs/src/operations/index.md`                               | Update                               | Document required questions, flags, errors, and breaking scope | `dstack-mol-a8i.1` |
| Development                | `docs/src/development/index.md`                              | Update                               | Document checker contract and matrix validation                | `dstack-mol-a8i.3` |
| Reference                  | `docs/src/reference/index.md`                                | Update                               | Record answers, flags, kinds, validation, and outputs          | `dstack-mol-a8i.1` |
| Navigation                 | `docs/src/SUMMARY.md`                                        | Update if new dstack pages are added | Keep dstack book current                                       | `dstack-mol-a8i.2` |
| Implemented Feature Record | `docs/src/features/010-purposeful-project-scaffold/index.md` | Create during close-out              | Preserve delivery evidence                                     | `dstack-mol-dyl`   |

Generated template documentation and tests are owned by the implementation tasks described below, not by the dstack
reader-page rows alone.

## Validation Strategy

- Parameterize all seven kinds through one render matrix.
- Use punctuation-heavy brief values and separately test whitespace/control-character rejection.
- Assert exact generated file sets, exact `SUMMARY.md` links, absence of the deleted landing pages, Copier answer
  parity, helper forwarding, and destination uniqueness.
- Parse generated TOML, run both checker copies through focused tests, and build every rendered mdBook.
- Preserve focused tests for broken links, unsafe/internal navigation, malformed feature records, missing registrations,
  `unsafe=False`, source recording, and no-overwrite routing.
- Run `mise exec -- uv run pytest -m "not external"` before specification reconciliation and the complete repository
  validation during feature close-out.

## Implementation Decomposition

1. `dstack-mol-a8i.1`: add and forward the exact structured inputs; update setup usage/reference docs and focused tests.
2. `dstack-mol-a8i.2`: render the shared factual book, kind guidance, and dstack architecture/overview/navigation docs.
3. `dstack-mol-a8i.3`: relax both checker copies, retain all other validation, and update checker-contract docs/tests.
4. `dstack-mol-a8i.4`: complete the seven-kind/punctuation/safety integration matrix and document its validation.

## Dependencies and Parallelism

`.2` depends on `.1`; `.3` depends on `.2` so template/checker tests may share `tests/test_repository.py` without
parallel edits; `.4` depends on `.2` and `.3`. The implementation coordinator remains blocked by `spec-reconcile`, so
all children inherit the specification gate through their parent. Direct child-to-spec edges are unnecessary and are
rejected by Beads as redundant traversal cycles.

## Rollout and Migration

Ship as a documented pre-1.0 breaking template improvement in the next tagged release. Do not add compatibility aliases,
fallback prose, or fabricated answers.

## Risks and Tradeoffs

The initial book is smaller and project kind has limited visible effect. This is deliberate: truthful omission is more
useful than a larger fictional scaffold, and `/plan-features` can add concrete pages once product intent exists.

## Rejected Alternatives

- A single free-form description: insufficient for truthful scope and boundaries.
- LLM-only inference: not deterministic across Copier updates.
- Seven kind-specific page trees: the brief lacks facts to populate them.
- Fixed empty section pages: misleading and contrary to explicit user intent.
- A checker that reads project kind: unnecessary because all absent concerns are valid.
- Pre-1.0 compatibility aliases/defaults: explicitly rejected by the user.

## Open Questions

None.

## Deferred Decisions

Additional project kinds and pre-v1 compatibility require a concrete consumer need. Language-specific tooling is F030;
monorepo layout is F050.

## Planning Record

### Questions Asked and Answers

The user approved a structured brief, the seven kinds, omission of content-free pages, required direct-helper inputs,
and breaking pre-1.0 changes. Isolated reviews required exact input/output contracts and identified that the brief
cannot truthfully populate kind-specific product pages.

### Assumptions

Documentation language remains English. Brief fields are intentionally single-line summaries, not arbitrary Markdown.

### Design Changes During Planning

Specification review narrowed seven kind-specific file trees to one minimal factual book with kind-specific future
concern guidance. It removed the redundant docs landing page, named all answer/flag contracts, scoped replacement-prose
rules, clarified checker behavior, made task ownership exact, and serialized checker work after rendering work.

### Source Material

Current template and dog-food docs; AtomixOS, Nixstasis, and Conduit layouts; four isolated F010 reviews recorded in
Beads.
