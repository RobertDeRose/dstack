# Design — Monorepo tooling layout

## Metadata

- Beads feature root: `dstack-mol-7s4`
- Feature slug: `monorepo-tooling-layout`
- Design path: `docs/src/features/monorepo-tooling-layout/design.md`
- Implemented record: `docs/src/features/monorepo-tooling-layout/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Add an explicit monorepo layout mode in which root configuration owns shared documentation and quality policy while
package-local mise configuration owns language-specific commands.

## User Intent

Monorepo support should follow the proven Nixstasis ownership pattern, but only after single-package language profiles
are stable.

## Goals

- Add single-package and monorepo layout answers.
- Keep root docs, hk, shared tools, and aggregate tasks authoritative.
- Generate package-local mise configuration from each package's selected language profiles.
- Scope hk checks and working directories to changed packages.
- Compose root tasks through declared dependencies.

## Non-Goals

- Discover or invent package boundaries without user input.
- Generate package source/manifests.
- Require experimental mise monorepo behavior unless no stable alternative exists.
- Support arbitrary nested workspace graphs initially.

## User-Facing Behavior

For monorepos, setup collects package paths and their language profiles, validates portable non-overlapping paths, and
renders shared root tooling plus package-local task ownership.

## Requirements

### Functional Requirements

- Layout defaults explicitly to single-package.
- Monorepo package paths are relative, normalized, unique, and cannot escape the repository.
- Root checks aggregate package checks without duplicating commands.
- hk globs and working directories prevent unrelated packages from paying validation cost.
- Documentation explains the generated repository map and canonical task entry points.

### Quality Requirements

- No experimental mise setting is used without implementation-time evidence that it remains required and supported.
- Mixed-language package matrices render without destination collisions.
- Root and package task names remain discoverable.

### Compatibility and Migration Requirements

This depends on stable profile composition from Language quality profiles. It may ship later without blocking
single-package adoption.

## Existing Context

Nixstasis demonstrates root tool ownership with package-local mise files and scoped hk steps. Its experimental setting
and concrete Go/Elixir commands are not suitable for direct copying.

## Proposed Design

Extend recorded answers with repository layout and a bounded package list. Render package-local configuration only in
monorepo mode. Prefer stable mise task inclusion/dependencies; evaluate experimental monorepo discovery only if required
by current mise.

## Architecture Consistency

### Existing Patterns Reused

Additive language profiles, root shared baseline, task dependencies, file globs, and explicit working directories.

### Invariants Preserved

The root remains the documentation and workflow authority; package configs cannot override Beads or feature identity.

### New Decisions Introduced

Monorepo structure is explicit user input and a later dependent capability, never inferred.

### Architecture Documentation Changes

Document root/package ownership and task resolution.

## Operational Considerations

Invalid or overlapping package paths fail before rendering. Package additions after setup require a Copier answer update
or project-owned extension.

## Documentation Impact

| Documentation concern      | Exact page                                           | Create or update                       | Planned change                      | Owning Beads task            |
|----------------------------|------------------------------------------------------|----------------------------------------|-------------------------------------|------------------------------|
| Architecture               | `docs/src/architecture/index.md`                     | Update                                 | Root/package ownership              | Monorepo tooling layout docs |
| Usage                      | `docs/src/operations/index.md`                       | Update                                 | Monorepo setup input                | Monorepo tooling layout docs |
| Development                | `docs/src/development/index.md`                      | Update                                 | Package tasks and validation        | Monorepo tooling layout docs |
| Reference                  | `docs/src/reference/index.md`                        | Update                                 | Layout answers and path constraints | Monorepo tooling layout docs |
| Navigation                 | `docs/src/SUMMARY.md`                                | Update if repository-layout page added | Register page                       | Monorepo tooling layout docs |
| Implemented Feature Record | `docs/src/features/monorepo-tooling-layout/index.md` | Create during close-out                | Delivery evidence                   | lifecycle close-out          |

## Validation Strategy

Render representative homogeneous and mixed-language monorepos; validate path rejection, task discovery, scoped checks,
root aggregation, no duplicated destinations, and docs accuracy. Compare stable and experimental mise approaches against
current official behavior.

## Implementation Decomposition

1. Research current stable mise monorepo/task composition behavior.
2. Add layout/package answer validation.
3. Render root/package configs and scoped hk composition.
4. Add matrix tests and reader documentation.

## Dependencies and Parallelism

Depends on Language quality profiles. Research can begin earlier; implementation waits for profile answer and
composition stability.

## Rollout and Migration

Deliver after single-package profiles have been exercised in generated projects.

## Risks and Tradeoffs

Package matrices can become open-ended. Initial support should enforce a bounded, flat package list and defer exotic
workspace layouts.

## Rejected Alternatives

- Default monorepo mode: needless complexity for most projects.
- Automatic package discovery: impossible in a new empty scaffold.
- Copy Nixstasis experimental configuration verbatim: version-sensitive and unverified.

## Open Questions

Whether current stable mise can discover package-local configs without its experimental monorepo mode must be resolved
during the research task.

## Deferred Decisions

Nested workspaces and package-specific deployment pipelines.

## Planning Record

### Questions Asked and Answers

The user agreed monorepo support should be a later dependent feature.

### Assumptions

A bounded flat package list covers the first real consumers.

### Design Changes During Planning

Monorepo support was removed from the first delivery sequence.

### Source Material

Nixstasis root/package mise layout and scoped hk configuration.
