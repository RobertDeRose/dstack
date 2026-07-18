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
- Preserve existing root and package hk/mise behavior during managed updates unless an exact replacement is reviewed.
- Make render/update plans explicit, observable, interruption-safe, and idempotent.

## Non-Goals

- Discover or invent package boundaries without user input.
- Generate package source/manifests.
- Require experimental mise monorepo behavior unless no stable alternative exists.
- Support arbitrary nested workspace graphs initially.

## User-Facing Behavior

For monorepos, setup collects canonical package names, paths, and language profiles, validates portable non-overlapping
paths, and renders shared root tooling plus package-local task ownership. Dry-run reports created, preserved, candidate,
conflicting, completed, and remaining package outputs; apply is a separate, unmistakable operation.

Switching an already managed single-package project to monorepo mode is explicit. Existing root/package hk and mise
configuration remains authoritative when generated output differs; generated replacements are staged as candidates for
review instead of overwriting project behavior. Repeated or interrupted application resumes from durable package-level
state and does not replay completed package mutations.

## Requirements

### Functional Requirements

- Layout defaults explicitly to single-package.
- Monorepo package paths are relative, normalized, unique, and cannot escape the repository.
- Root checks aggregate package checks without duplicating commands.
- hk globs and working directories prevent unrelated packages from paying validation cost.
- Documentation explains the generated repository map and canonical task entry points.
- Package names and reader-facing titles preserve explicit user capitalization and technical acronyms.
- Managed single-package projects may enter monorepo mode only through an explicit layout/package answer update.
- Existing differing root/package hk and mise files are preserved; generated versions become reviewable candidates.
- Dry-run never applies changes; apply announces its start and reports package/output progress.
- Interrupted apply resumes incomplete packages without rewriting completed package output.
- Implemented-feature and package navigation updates are bounded to managed marker regions and byte-idempotent.

### Quality Requirements

- No experimental mise setting is used without implementation-time evidence that it remains required and supported.
- Mixed-language package matrices render without destination collisions.
- Root and package task names remain discoverable.
- A representative larger flat package matrix has bounded render time and proves unrelated packages avoid validation.
- Repeated render/update and recovery fixtures assert byte-stable output and mutation work proportional to what remains.

### Compatibility and Migration Requirements

This depends on stable profile composition from Language quality profiles and the native runner contract from hk policy
simplification. It may ship later without blocking single-package adoption. Existing Copier answers without a layout
field default to `single-package`; no package-local files are introduced until the user explicitly selects monorepo mode
and supplies the complete bounded package list.

## Existing Context

Nixstasis demonstrates root tool ownership with package-local mise files and scoped hk steps. Its experimental setting
and concrete Go/Elixir commands are not suitable for direct copying.

## Proposed Design

Extend recorded answers with repository layout and a bounded package list. Render package-local configuration only in
monorepo mode. Prefer stable mise task inclusion/dependencies. A timeboxed compatibility spike records current official
mise evidence and selects, in order, stable includes, explicit root task composition, or a narrowly isolated supported
fallback; every outcome preserves the same root/package ownership and task contract, so no product decision is deferred.

Reuse candidate reconciliation and durable progress patterns from migration safety rather than adding silent overwrite
or one-shot behavior. Keep setup rendering deterministic and updates additive; do not copy migration archives,
checkpoint-evidence schema, or other legacy-only machinery into new-project setup.

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

Invalid or overlapping package paths fail before rendering. Package additions after setup require an explicit Copier
answer update. Preflight shows exact ownership/collision evidence before apply; failures preserve the worktree and
report the package/output, reproduction command, and resume command.

## Documentation Impact

| Documentation concern      | Exact page                                           | Create or update                       | Planned change                                                          | Owning Beads task     |
|----------------------------|------------------------------------------------------|----------------------------------------|-------------------------------------------------------------------------|-----------------------|
| Architecture               | `docs/src/architecture/index.md`                     | Update                                 | Root/package ownership and additive candidate boundary                  | `.7`, `.9` reconciles |
| Usage                      | `docs/src/operations/index.md`                       | Update                                 | Explicit inputs, dry-run/apply, progress, recovery, candidate decisions | `.6`, `.7`, `.9`      |
| Development                | `docs/src/development/index.md`                      | Update                                 | mise evidence, package tasks, scale/recovery validation                 | `.5`, `.8`, `.9`      |
| Reference                  | `docs/src/reference/index.md`                        | Update                                 | Exact answers, paths, states, commands, defaults, candidate fields      | `.5`–`.7`, `.9`       |
| Navigation                 | `docs/src/SUMMARY.md`                                | Update if repository-layout page added | Register page and bounded managed navigation                            | `.7`, `.9`            |
| Implemented Feature Record | `docs/src/features/monorepo-tooling-layout/index.md` | Create during close-out                | Delivery evidence                                                       | lifecycle close-out   |

## Validation Strategy

- Render representative homogeneous and mixed-language monorepos; validate path rejection, task discovery, scoped
  checks, root aggregation, no duplicated destinations, acronym preservation, and docs accuracy.
- Compare supported mise composition approaches against current official behavior in a timeboxed compatibility fixture.
- Upgrade an older managed single-package answer set only after explicit monorepo selection; preserve differing existing
  root/package hk and mise files as candidates.
- Exercise dry-run/apply separation, package-level progress, interrupted apply, byte-idempotent retry, and exact
  recovery.
- Render a larger bounded flat package matrix and assert unrelated package checks do not run and retries touch only
  incomplete/conflicting outputs.
- Regenerate package/feature navigation within managed markers and assert unchanged rerenders are byte-stable.
- Run focused matrix/update/recovery tests, documentation checks, `HK_JOBS=1 mise run check`, and the canonical full
  suite.

## Implementation Decomposition

1. `dstack-mol-5bq.5` **mise compatibility spike:** timebox current official composition evidence and record the
   supported implementation path without changing the established ownership/task contract.
2. `dstack-mol-5bq.6` **layout contract:** add canonical layout/package answers, path/name/profile validation,
   legacy-answer defaulting, explicit single-package conversion, dry-run/apply separation, and package
   progress/recovery.
3. `dstack-mol-5bq.7` **additive rendering:** render root/package configs and scoped hk composition while preserving
   differing existing files through candidate reconciliation and bounded navigation updates.
4. `dstack-mol-5bq.8` **scale and recovery:** add homogeneous/mixed/large matrices, unrelated-package scoping,
   interrupted update, proportional retry, idempotence, and existing-config preservation tests.
5. `dstack-mol-5bq.9` **reader documentation and integration:** publish exact contracts and aggregate the bounded
   fixtures into final integration evidence.

## Dependencies and Parallelism

Depends on Language quality profiles and hk policy simplification, both delivered. Tasks are ordered spike → layout
contract → additive rendering → scale/recovery → integration because they share answer schemas, templates, and fixtures.
Every task depends directly on specification reconciliation and owns one reviewed commit.

## Rollout and Migration

Deliver after single-package profiles have been exercised in generated projects.

## Risks and Tradeoffs

Package matrices can become open-ended. Initial support enforces a bounded, flat package list and defers exotic
workspace layouts. Candidate reconciliation adds an explicit review step but prevents update-time behavior loss. Durable
progress adds state, but package-level phases keep interruption recovery understandable and avoid replaying large
renders.

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
identity, additive update reconciliation, dry-run/apply visibility, durable progress, interruption recovery, bounded
large-matrix validation, acronym preservation, and managed navigation requirements. Legacy-only archives and checkpoint
machinery remain out of scope.

### Source Material

Nixstasis root/package mise layout and scoped hk configuration.
