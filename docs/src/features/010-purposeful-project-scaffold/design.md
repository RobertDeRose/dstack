# Design — F010 Purposeful project scaffold

## Metadata

- Beads feature root: `dstack-mol-ln9`
- Feature number: `010`
- Feature slug: `purposeful-project-scaffold`
- Design path: `docs/src/features/010-purposeful-project-scaffold/design.md`
- Implemented record: `docs/src/features/010-purposeful-project-scaffold/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Make `/setup-project` collect a concrete project brief and kind, then render useful project-specific mdBook navigation
and content without replacement-style section pages.

## User Intent

dstack should dog-food its documentation-first workflow. New projects should begin with truthful documentation rather
than prose telling maintainers what to write later.

## Goals

- Require purpose, intended users, current scope, and key boundaries for new setup.
- Support project kinds: library, CLI, service, application, infrastructure, documentation, and other.
- Render known facts into README, book metadata, overview, and applicable navigation.
- Omit pages without concrete content.
- Keep answers deterministic and recorded by Copier.

## Non-Goals

- Generate application source code or framework-specific architecture.
- Infer unconfirmed project facts from a name.
- Preserve pre-1.0 setup CLI compatibility.
- Change migration or update authority boundaries.

## User-Facing Behavior

The setup skill asks one brief question at a time, confirms project kind, and invokes the helper with explicit brief
fields. Direct helper invocation requires the same inputs. The resulting book contains only useful pages selected for
that project kind.

## Requirements

### Functional Requirements

- Both Copier entrypoints define identical brief and project-kind answers.
- `setup-project.py` requires and forwards all brief fields and project kind.
- Markdown and TOML rendering safely handle punctuation and quotes.
- `SUMMARY.md` and generated files vary deterministically by project kind.
- Documentation validation accepts omitted inapplicable concerns while strictly validating all present pages and feature
  records.

### Quality Requirements

- No generated reader page contains "describe", "explain", "add content", or equivalent replacement guidance.
- Setup safety, `unsafe=False`, source recording, and no-overwrite behavior remain intact.
- Every project-kind render passes the docs checker and mdBook build.

### Compatibility and Migration Requirements

Pre-1.0 compatibility is not required. Copier answers still use stable names so later updates can preserve project
intent.

## Existing Context

The current template accepts one generic description, emits fixed section indexes containing authoring prompts, and
requires all documentation concerns in `SUMMARY.md`. dstack now dog-foods a concrete mdBook and shared docs validation.

## Proposed Design

Add structured Copier answers and matching required CLI flags. Keep authoring guidance in documentation conventions. Use
project-kind conditionals for filenames, navigation, and initial reader journeys. Populate the overview directly from
the brief. Keep workflow pages, roadmap, feature index, and documentation conventions universal.

## Architecture Consistency

### Existing Patterns Reused

Copier answer parity, explicit helper forwarding, conditional filenames, bundled-template authority, and
`scripts/check-docs.py` validation.

### Invariants Preserved

Setup remains new-project-only, deterministic, non-overwriting, and offline with respect to template source.

### New Decisions Introduced

Project kind controls documentation information architecture; unknown content is omitted rather than represented by
placeholder prose.

### Architecture Documentation Changes

Update `docs/src/architecture/index.md` with the new setup-input and rendering boundary.

## Operational Considerations

Direct invocation becomes intentionally stricter. Errors must name missing brief fields and accepted project kinds.

## Documentation Impact

| Documentation concern      | Exact page                                                   | Create or update        | Planned change                                | Owning Beads task   |
|----------------------------|--------------------------------------------------------------|-------------------------|-----------------------------------------------|---------------------|
| Introduction               | `docs/src/introduction/project-overview.md`                  | Update                  | Document structured project brief             | F010 docs           |
| Architecture               | `docs/src/architecture/index.md`                             | Update                  | Document kind-aware rendering                 | F010 docs           |
| Usage                      | `docs/src/operations/index.md`                               | Update                  | Document required setup interaction and flags | F010 docs           |
| Development                | `docs/src/development/index.md`                              | Update                  | Document template matrix validation           | F010 docs           |
| Reference                  | `docs/src/reference/index.md`                                | Update                  | Record new answers and CLI contract           | F010 docs           |
| Navigation                 | `docs/src/SUMMARY.md`                                        | Update if needed        | Register durable pages                        | F010 docs           |
| Implemented Feature Record | `docs/src/features/010-purposeful-project-scaffold/index.md` | Create during close-out | Preserve delivery evidence                    | lifecycle close-out |

## Validation Strategy

Render all seven project kinds with punctuation-heavy brief values; run generated docs checks and mdBook builds; run
static and integration pytest suites; check both Copier entrypoints remain aligned and conditional destinations do not
collide.

## Implementation Decomposition

1. Add and forward structured setup inputs.
2. Replace placeholder templates with kind-aware useful pages/navigation.
3. Relax and test docs concern validation without weakening link/feature checks.
4. Update dstack reader documentation.

## Dependencies and Parallelism

Template rendering follows input/schema work. Documentation and checker work can proceed in parallel after answer names
stabilize.

## Rollout and Migration

Ship as a pre-1.0 breaking template improvement in the next tagged release.

## Risks and Tradeoffs

More Copier conditionals increase the render matrix. Constrained kinds and centralized shared pages limit duplication.

## Rejected Alternatives

- A single free-form description: insufficient for truthful scope and boundaries.
- LLM-only inference: not deterministic across Copier updates.
- Fixed empty section pages: preserves navigation at the cost of misleading documentation.

## Open Questions

None.

## Deferred Decisions

Additional project kinds may be added only after a concrete consumer requires them.

## Planning Record

### Questions Asked and Answers

The user approved a structured brief, the seven recommended project kinds, omission of content-free pages, and required
direct-helper inputs.

### Assumptions

The documentation language remains English; implementation-language profiles are separate.

### Design Changes During Planning

Compatibility preservation was explicitly dropped because dstack is pre-1.0.

### Source Material

Current template and dog-food docs; AtomixOS, Nixstasis, and Conduit documentation layouts.
