# Design — F030 Language quality profiles

## Metadata

- Beads feature root: `dstack-mol-ni2`
- Feature number: `030`
- Feature slug: `language-quality-profiles`
- Design path: `docs/src/features/030-language-quality-profiles/design.md`
- Implemented record: `docs/src/features/030-language-quality-profiles/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Let new projects select Python, TypeScript, Rust, Go, Elixir, Nix, or none/other profiles that extend the universal
mise/hk baseline without generating application code.

## User Intent

Setup should optimize quality tooling for the implementation languages while remaining a workflow scaffold rather than
an application generator. TypeScript projects should use Aube.

## Goals

- Support a list of selected language profiles.
- Add only relevant mise tools, hk steps, ignore rules, and concrete development guidance.
- Use Aube for TypeScript package operations.
- Permit none/other as a complete valid configuration.
- Scope checks by file glob so unrelated work avoids unnecessary validation.

## Non-Goals

- Generate package manifests, source files, frameworks, APIs, or build architecture.
- Support JavaScript as a separate profile.
- Introduce monorepo behavior in this feature.

## User-Facing Behavior

The setup skill confirms implementation languages. Generated tooling recognizes matching files when they appear, while
projects with no selected profile retain the full universal documentation and repository hygiene baseline.

## Requirements

### Functional Requirements

- Copier records a deterministic list drawn from Python, TypeScript, Rust, Go, Elixir, Nix, and none/other.
- Each profile declares every executable used by its hk steps.
- Python uses uv-based execution with Ruff and type checking.
- TypeScript provisions Node and Aube, with Aube as the package/script entry point.
- Rust, Go, Elixir, and Nix use their native format/lint/test conventions without creating manifests.
- Conditional template outputs have no destination collisions for any supported combination.

### Quality Requirements

- Profile steps skip cleanly when no matching files exist.
- Shared configuration is not duplicated per language.
- Generated development documentation states only commands the selected profile actually provides.

### Compatibility and Migration Requirements

Pre-1.0 answer changes are allowed. Existing generated projects may select profiles during a later Copier update.

## Existing Context

F020 establishes the shared baseline. Surveyed repositories demonstrate scoped globs and working directories, but their
concrete language commands must not be copied blindly.

## Proposed Design

Represent profiles as Copier data and render additive tool entries, hk mappings, ignore fragments, and development
reference sections. Keep one common mise/hk file. Validate the complete profile matrix programmatically.

## Architecture Consistency

### Existing Patterns Reused

Mise as tool owner, hk built-ins, file-scoped steps, and Copier conditionals.

### Invariants Preserved

Language selection affects tooling only; workflow lifecycle, authority, and docs validation remain language-agnostic.

### New Decisions Introduced

TypeScript uses Aube rather than npm, pnpm, or Yarn. JavaScript is not a separate supported profile.

### Architecture Documentation Changes

Document additive profile composition and the boundary against application scaffolding.

## Operational Considerations

Aube automatically installs dependencies when scripts run and can use existing lockfiles. Setup must not execute project
scripts because no application manifest is generated.

## Documentation Impact

| Documentation concern      | Exact page                                                 | Create or update        | Planned change                      | Owning Beads task   |
|----------------------------|------------------------------------------------------------|-------------------------|-------------------------------------|---------------------|
| Architecture               | `docs/src/architecture/index.md`                           | Update                  | Profile composition boundary        | F030 docs           |
| Usage                      | `docs/src/operations/index.md`                             | Update                  | Language selection                  | F030 docs           |
| Development                | `docs/src/development/index.md`                            | Update                  | Profile commands and matrix testing | F030 docs           |
| Reference                  | `docs/src/reference/index.md`                              | Update                  | Supported profiles and tools        | F030 docs           |
| Navigation                 | `docs/src/SUMMARY.md`                                      | Update if pages added   | Register any profile reference page | F030 docs           |
| Implemented Feature Record | `docs/src/features/030-language-quality-profiles/index.md` | Create during close-out | Delivery evidence                   | lifecycle close-out |

## Validation Strategy

Render each profile alone, none/other, and representative mixed profiles; validate TOML/Pkl, tool resolution, hk config,
globs, tasks, documentation claims, and conditional destination uniqueness.

## Implementation Decomposition

1. Add profile answer and composition helpers.
2. Add Python/TypeScript profiles.
3. Add Rust/Go/Elixir/Nix profiles.
4. Add matrix tests and documentation.

## Dependencies and Parallelism

Depends on F020. Python/TypeScript and Rust/Go/Elixir/Nix can be implemented in parallel after the composition contract
stabilizes.

## Rollout and Migration

Ship profiles incrementally behind the same stable answer values; none/other remains the fallback.

## Risks and Tradeoffs

Mixed profiles expand the render matrix. Additive fragments and automated matrix validation contain the risk.

## Rejected Alternatives

- Framework starters: outside dstack's ownership.
- A JavaScript profile: user explicitly requested TypeScript only.
- npm: rejected in favor of Aube.
- One complete template per language: excessive drift and duplication.

## Open Questions

None.

## Deferred Decisions

Additional languages require a demonstrated consumer and complete mise/hk validation contract.

## Planning Record

### Questions Asked and Answers

The user approved Python, TypeScript, Rust, Go, Elixir, Nix, and none/other; selected Aube for TypeScript; and rejected
source/package scaffolding.

### Assumptions

Multiple language profiles may be selected for a single-package repository.

### Design Changes During Planning

JavaScript was narrowed to TypeScript and npm was replaced by Aube.

### Source Material

Aube official documentation and scoped hook patterns from Nixstasis and Conduit.
