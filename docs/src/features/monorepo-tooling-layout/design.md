# Design — Monorepo tooling layout

## Metadata

- Beads feature root: `dstack-mol-7s4`
- Feature slug: `monorepo-tooling-layout`
- Design path: `docs/src/features/monorepo-tooling-layout/design.md`
- Implemented record: `docs/src/features/monorepo-tooling-layout/index.md`
- Base branch: `main`
- Status: reviewed

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
- Preserve existing root and package hk/mise behavior during managed updates unless an exact replacement is reviewed.
- Make setup/update preflight explicit and renders byte-idempotent without adding a second scaffold-state authority.

## Non-Goals

- Discover or invent package boundaries without user input.
- Generate package source/manifests.
- Require experimental mise monorepo behavior unless no stable alternative exists.
- Support arbitrary nested workspace graphs initially.

## User-Facing Behavior

For monorepos, setup collects canonical package display names, slugs, paths, and language profiles, validates portable
non-overlapping paths, and renders shared root tooling plus package-local task ownership. Root `mise.toml` owns the
union of tools and aggregate tasks; package-local mise files own package commands and working directories; root hk owns
scoped pre-commit dispatch. `mise run check` validates every declared package, while pre-commit scopes work by changed
paths.

Switching an already managed single-package project to monorepo mode is explicit. Normal managed updates continue using
Copier preview/three-way conflict behavior. Candidate files are used only when introducing a generated package-local
path that is already occupied by a non-Copier project file; Copier-managed root files are never diverted into a second
update protocol. Repeated preview/render/update is byte-idempotent.

## Requirements

### Functional Requirements

- Layout defaults explicitly to single-package.
- Monorepo package paths are relative, normalized, unique, and cannot escape the repository.
- Root checks aggregate package checks without duplicating commands.
- hk globs and working directories prevent unrelated packages from paying validation cost.
- Documentation explains the generated repository map and canonical task entry points.
- Package names and reader-facing titles preserve explicit user capitalization and technical acronyms.
- Managed single-package projects may enter monorepo mode only through an explicit layout/package answer update.
- Copier-managed files use Copier three-way conflicts; candidates apply only when a newly generated package-local path
  is occupied by a non-Copier project file.
- Existing setup/update preflight reports package inputs, generated destinations, and collisions before mutation.
- Root `mise run check` validates all declared packages; changed-package scoping applies only to pre-commit.
- Generated repository-layout documentation is one Copier-owned page and byte-idempotent; no new marker framework is
  introduced.

### Quality Requirements

- No experimental mise setting is used without implementation-time evidence that it remains required and supported.
- Mixed-language package matrices render without destination collisions.
- Root and package task names remain discoverable.
- A representative larger flat package matrix has bounded render time and proves unrelated packages avoid pre-commit
  validation while full `check` still covers all packages.
- Repeated render/update fixtures assert byte-stable output and existing Copier conflict recovery.

### Compatibility and Migration Requirements

This depends on stable profile composition from Language quality profiles and the native runner contract from hk policy
simplification. It may ship later without blocking single-package adoption. Existing Copier answers without a layout
field default to `single-package`; no package-local files are introduced until the user explicitly selects monorepo mode
and supplies the complete bounded package list. Version 1 supports at most 32 flat packages.

#### Package answer and path contract

`repository_layout` is `single-package` or `monorepo`, defaulting to `single-package`. `monorepo_packages` is empty in
single-package mode and contains 1–32 objects in monorepo mode:

- `display_name`: nonempty reader-facing text preserved exactly, including technical acronyms;
- `slug`: explicit lowercase filesystem/task-safe `[a-z0-9]+(?:-[a-z0-9]+)*`, unique under Unicode case-folding;
- `path`: normalized relative POSIX directory path used as the package root;
- `language_profiles`: nonempty canonical profile list using the delivered profile validation and `other` exclusivity.

Paths must be unique, case-fold unique, non-absolute, nonempty, and free of `.`/`..` components. Package roots cannot be
ancestor/descendant pairs, resolve through symlinks, or equal root-owned `.git`, `.beads`, `docs`, `migration`,
`scripts`, `skills`, or their descendants. Package source/manifests remain project-owned inside valid package roots.

#### Tool, task, lock, and provisioning ownership

A monorepo retains exactly one root `mise.lock` and one root `scripts/setup-tooling.py`. Root `mise.toml` declares the
union of tools required by all package profiles and aggregate tasks. Package-local mise files declare package commands,
working directories, and task metadata but no independently locked tool versions. The root provisioner remains the only
lock/install/hook authority and preserves the existing four-platform lock and Nix host exception.

Root `mise run check` and CI validate all packages. Root hk uses package path globs to dispatch package-local commands
for changed files during pre-commit; shared/root file changes run shared policy and any explicitly affected aggregate
checks. `fix` follows the same changed-path package scoping. A future explicit `check:changed` task is out of scope.

## Existing Context

Nixstasis demonstrates root tool ownership with package-local mise files and scoped hk steps. Its experimental setting
and concrete Go/Elixir commands are not suitable for direct copying.

## Proposed Design

Extend recorded answers with repository layout and the exact bounded package schema. Render package-local configuration
only in monorepo mode. Prefer stable mise task inclusion/dependencies. A timeboxed compatibility spike verifies package
task discovery plus participation in the single root lock/install path and selects, in order, stable includes, explicit
root task composition, or a narrowly isolated supported fallback. Every outcome preserves the fixed ownership, task,
lock, and provisioner contract, so no product decision is deferred.

Reuse explicit input, preflight, additive preservation, and idempotence lessons from migration safety without importing
its durable progress state. Keep Copier as scaffold/update authority: ordinary managed changes use its three-way merge;
only collisions at newly introduced non-Copier package-local destinations create candidates under the existing
`migration/copier-adoption-candidates/<same-relative-path>` convention. Do not copy migration archives,
checkpoint-evidence schema, or a separate resume manifest into setup/update.

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

Invalid, reserved, symlinked, case-colliding, or overlapping package paths fail before rendering. Package additions
after setup require an explicit Copier answer update. Setup/update preflight shows exact package answers, destinations,
and collisions. Copier conflicts preserve the worktree and use the existing update recovery command; newly occupied
non-Copier package destinations are preserved with a candidate at the same relative path.

Generated monorepos include Copier-owned `docs/src/reference/repository-layout.md`, listing root/package ownership,
package paths/profiles, full-check behavior, and canonical package task names. The generated `docs/src/SUMMARY.md.jinja`
includes that page only in monorepo mode. Because Copier owns the whole generated page, no package-navigation marker or
repository-level package navigation is introduced.

## Documentation Impact

| Documentation concern      | Exact page                                                                                                                                 | Create or update        | Planned change                                                             | Owning Beads task     |
|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|-------------------------|----------------------------------------------------------------------------|-----------------------|
| Architecture               | `docs/src/architecture/index.md`                                                                                                           | Update                  | Root/package ownership and additive candidate boundary                     | `.7`, `.9` reconciles |
| Usage                      | `docs/src/operations/index.md`                                                                                                             | Update                  | Explicit inputs, preflight, Copier conflicts/recovery, candidate decisions | `.6`, `.7`, `.9`      |
| Development                | `docs/src/development/index.md`                                                                                                            | Update                  | mise evidence, package tasks, scale/recovery validation                    | `.5`, `.8`, `.9`      |
| Reference                  | `docs/src/reference/index.md`                                                                                                              | Update                  | Exact answers, paths, states, commands, defaults, candidate fields         | `.5`–`.7`, `.9`       |
| Generated layout reference | `skills/setup-project/template/docs/src/reference/repository-layout.md.jinja`                                                              | Create                  | Package map, ownership, tasks, full/changed scope                          | `.7`, `.9`            |
| Generated navigation       | `skills/setup-project/template/docs/src/SUMMARY.md.jinja`                                                                                  | Update                  | Register layout reference only in monorepo mode                            | `.7`, `.9`            |
| Generated tooling docs     | `skills/setup-project/template/docs/src/development/tooling.md.jinja`; `skills/setup-project/template/docs/src/reference/tooling.md.jinja` | Update                  | Package task and exact tooling contracts                                   | `.7`, `.9`            |
| Skill procedures           | `skills/setup-project/SKILL.md`; `skills/update-project/SKILL.md`                                                                          | Update                  | Inputs, conversion, preflight, conflicts, recovery                         | `.6`, `.7`, `.9`      |
| Implemented Feature Record | `docs/src/features/monorepo-tooling-layout/index.md`                                                                                       | Create during close-out | Delivery evidence                                                          | lifecycle close-out   |

## Validation Strategy

- Render representative homogeneous and mixed-language monorepos; validate path rejection, task discovery, scoped
  checks, root aggregation, no duplicated destinations, acronym preservation, and docs accuracy.
- Compare supported mise task composition and single-root lock/install behavior against current official behavior in a
  timeboxed compatibility fixture.
- Upgrade an older managed single-package answer set only after explicit monorepo selection; exercise Copier preview,
  three-way conflict recovery, and candidate preservation only for newly occupied non-Copier package destinations.
- Validate the 32-package limit, exact schema, case-fold collisions, overlap, reserved paths, and symlink rejection.
- Render a larger bounded flat package matrix and assert unrelated package pre-commit checks do not run while root
  `mise run check` validates every package.
- Regenerate the Copier-owned repository-layout page/navigation and assert unchanged rerenders are byte-stable.
- Run focused matrix/update/recovery tests, documentation checks, `HK_JOBS=1 mise run check`, and the canonical full
  suite.

## Implementation Decomposition

1. `dstack-mol-5bq.5` **mise compatibility spike:** timebox current official composition evidence and record the
   supported implementation path without changing the established ownership/task contract.
2. `dstack-mol-5bq.6` **layout contract:** add the exact layout/package schema, path/name/profile validation,
   legacy-answer defaulting, explicit single-package conversion, and setup/update preflight.
3. `dstack-mol-5bq.7` **additive rendering:** render one root tool/lock authority, package tasks, scoped pre-commit hk,
   Copier conflict/candidate behavior, and the Copier-owned repository-layout page.
4. `dstack-mol-5bq.8` **scale and update safety:** add homogeneous/mixed/32-package matrices, full-check versus
   pre-commit scoping, conflict recovery, candidate preservation, and byte-idempotence tests.
5. `dstack-mol-5bq.9` **reader documentation and integration:** publish exact contracts and aggregate the bounded
   fixtures into final integration evidence.

## Dependencies and Parallelism

Depends on Language quality profiles and hk policy simplification, both delivered. Tasks are ordered spike → layout
contract → additive rendering → scale/update safety → integration because they share answer schemas, templates, and
fixtures. Every task depends directly on specification reconciliation and owns one reviewed commit.

## Rollout and Migration

Deliver after single-package profiles have been exercised in generated projects.

## Risks and Tradeoffs

Package matrices can become open-ended. Initial support enforces a bounded, flat package list and defers exotic
workspace layouts. Copier's existing three-way conflicts remain the managed-update mechanism; candidates are limited to
new package destinations occupied by non-Copier files. This avoids a second scaffold-state authority while preventing
behavior loss.

## Rejected Alternatives

- Default monorepo mode: needless complexity for most projects.
- Automatic package discovery: impossible in a new empty scaffold.
- Copy Nixstasis experimental configuration verbatim: version-sensitive and unverified.

## Open Questions

None. Current mise capability is an implementation fact handled by the compatibility spike; all supported outcomes must
satisfy the already-decided ownership and task-resolution contract.

## Deferred Decisions

Nested workspaces and package-specific deployment pipelines. Automatic package discovery remains excluded unless a later
feature establishes a safe, user-confirmed contract.

## Planning Record

### Questions Asked and Answers

The user agreed monorepo support should be a later dependent feature.

### Assumptions

A bounded flat package list covers the first real consumers.

### Design Changes During Planning

Monorepo support was removed from the first delivery sequence. Production migration evidence later added explicit
identity, explicit preflight, additive update preservation, bounded large-matrix validation, acronym preservation, and
Copier-owned navigation requirements. Review rejected migration-style durable progress/candidate machinery for ordinary
managed file rendering; legacy-only archives, checkpoint state, and a second scaffold authority remain out of scope.

### Source Material

Nixstasis root/package mise layout and scoped hk configuration.
