# Design — hk policy simplification

## Metadata

- Beads feature root: `dstack-mol-5v0`
- Feature slug: `hk-policy-simplification`
- Design path: `docs/src/features/hk-policy-simplification/design.md`
- Implemented record: `docs/src/features/hk-policy-simplification/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Replace the generated and repository hk policies' unnecessary command overrides and broad dependency chain with hk
built-ins, native config discovery, and file-level locking while restoring observable Harper commit-message linting.

## User Intent

The user expects dstack to add a small quality baseline without fighting hk's native behavior. Existing checks must not
silently disappear, `depends` must be exceptional rather than the default, built-ins should own standard tools, and
commit-message grammar checks must have executable proof.

## Goals

- Use `Builtins.harper_commit_message` without the current rule-disabling command override.
- Prefer hk built-ins and each tool's standard config discovery where behavior matches the contract.
- Remove dependency edges used only to serialize overlapping files; rely on hk read/write locks.
- Retain custom steps only for project-specific behavior and document why each remains custom.
- Preserve every supported validation capability across root and generated policies.
- Prove check, fix, pre-commit, and commit-msg behavior through representative generated projects.

## Non-Goals

- Replace hk, change its pinned binary/Pkl version, or redesign mise provisioning.
- Remove project-specific semantic documentation checks or manifest-gated language tests merely to reduce line count.
- Introduce a general step registry, Pkl generator, or second hook runner.
- Change language-profile selection, task names, application manifests, or GitHub workflow behavior.

## User-Facing Behavior

Generated projects retain the same six mise tasks and hooks. Checks and deterministic fixes run with greater native
parallelism. Harper rejects representative spelling, repetition, and agreement defects while accepting valid
Conventional Commit subjects and optional canonical Beads footers. Documentation lists the actual checks without
claiming artificial ordering.

## Requirements

### Functional Requirements

#### Native commit-message linting

Both root and generated `hk.pkl` use `Builtins.harper_commit_message` directly unless an upstream incompatibility is
proved by a failing fixture. Tests invoke the real `commit-msg` hook with:

- a valid scoped Conventional Commit subject;
- a valid subject plus final `Beads:` footer;
- repeated words;
- a representative spelling error;
- pronoun/verb disagreement.

The first two pass and the invalid fixtures fail specifically because of Harper. Cocogitto, subject/body length,
required scope, and Beads footer checks remain independently covered.

#### Built-in and config-discovery policy

For every current custom step, implementation records one disposition:

1. use the hk built-in unchanged;
2. use the built-in with the smallest necessary project-specific field override; or
3. retain a custom step because no built-in represents required behavior.

Rumdl uses normal `.config/rumdl.toml` discovery rather than an explicit default config argument. Equivalent redundant
flags are removed. The semantic documentation validator, commit footer rules, and manifest prerequisite guards may
remain custom because they are dstack-specific.

#### Dependency policy

Remove the global dependency chain that serializes unrelated steps. hk's file-level read/write locking owns ordinary
overlap between checks and fixers. A remaining `depends` edge is allowed only when one step consumes another step's
output or the final content is order-sensitive; its rationale must appear in design/reference documentation and a test.
No dependency may exist solely to force a stable display order or avoid a race hk already prevents.

#### Capability preservation

Capture the intended root and generated step inventories before refactoring. The final policies must retain all
supported universal, profile, manifest, commit-message, and repository-specific checks. Renaming a step requires an
explicit mapping in tests; deleting a capability requires separate user approval.

### Quality Requirements

- Root and rendered Pkl evaluate successfully.
- `hk check`, `hk fix`, pre-commit, and commit-msg fixtures are deterministic.
- Fix followed by check converges without unstaged-work loss.
- Representative single-profile, polyglot, and `other` projects retain selected-only behavior.
- Tests assert behavior and capability sets rather than the removed dependency implementation.

### Compatibility and Migration Requirements

Existing Copier-managed projects receive the simpler policy through normal three-way update. Project-owned hk
customizations remain subject to Copier conflict handling and the additive protections owned by Migration safety and
clarity. Task names, tool answers, and lock platforms do not change.

## Existing Context

Universal project tooling introduced one generated `hk.pkl`; Language quality profiles extended it with conditional
steps. A later race fix serialized nearly every step with `depends`, despite hk 1.49 coordinating overlapping fixers
through file-level read/write locks. Rumdl and Harper were replaced with custom commands, including a Harper ignore list
that disables major rule classes. Current tests assert the dependency chain and command strings rather than the desired
native behavior.

## Proposed Design

Keep one direct Pkl mapping shared by check, fix, and pre-commit. Replace standard custom steps with built-ins, remove
non-semantic dependencies, and let hk lock matching files. Keep small custom definitions only for dstack-specific
semantic checks, manifest gates, or tools without a suitable built-in. Test the public hook behavior directly.

## Architecture Consistency

### Existing Patterns Reused

The feature keeps the single mise/hk interface, version-coupled hk pin, profile-gated template sections, root-manifest
gates, and generated tooling documentation.

### Invariants Preserved

`check` remains read-only; `fix` and pre-commit remain deterministic; pre-commit retains `stash = "git"`; tests do not
run during pre-commit/fix except the existing explicit Go tidy behavior; generated projects keep six task names.

### New Decisions Introduced

hk native locking is authoritative for ordinary fixer coordination. Custom step definitions and dependency edges now
require a concrete behavioral justification.

### Architecture Documentation Changes

`docs/src/architecture/index.md` will describe native locking and the narrow custom-step boundary.

## Operational Considerations

The simplified graph may expose latent non-convergent tool combinations previously hidden by a fixed chain. The final
matrix therefore runs fix then check and reports any genuine order-sensitive exception. Harper failures must name the
lint so contributors can correct the message rather than bypass the hook.

## Documentation Impact

| Documentation concern      | Exact page                                                            | Create or update        | Planned change                                          | Owning Beads task   |
|----------------------------|-----------------------------------------------------------------------|-------------------------|---------------------------------------------------------|---------------------|
| Architecture               | `docs/src/architecture/index.md`                                      | Update                  | Native lock and customization boundary                  | `dstack-mol-v8c.2`  |
| Usage / Operations         | Not applicable                                                        | —                       | Contributor behavior is development/reference material  | —                   |
| Development                | `docs/src/development/index.md`                                       | Update                  | Hook behavior, Harper fixtures, and validation workflow | `dstack-mol-v8c.3`  |
| Reference                  | `docs/src/reference/index.md`                                         | Update                  | Exact retained custom steps and dependency exceptions   | `dstack-mol-v8c.3`  |
| Generated Development      | `skills/setup-project/template/docs/src/development/tooling.md.jinja` | Update                  | Native check/fix behavior                               | `dstack-mol-v8c.3`  |
| Generated Reference        | `skills/setup-project/template/docs/src/reference/tooling.md.jinja`   | Update                  | Actual steps and any justified ordering                 | `dstack-mol-v8c.3`  |
| Navigation                 | `docs/src/SUMMARY.md`                                                 | Update design markers   | Register this design                                    | planning            |
| Implemented Feature Record | `docs/src/features/hk-policy-simplification/index.md`                 | Create during close-out | Preserve delivery and audit history                     | lifecycle close-out |

## Validation Strategy

- Evaluate root and representative rendered Pkl.
- Invoke real commit-msg hooks with valid and invalid Harper fixtures.
- Compare pre/post capability inventories.
- Exercise check/fix/pre-commit convergence with overlapping Markdown and language files.
- Render both Copier entrypoints for `other`, representative single profiles, and one polyglot profile.
- Run focused tests while iterating, then the full repository suite, `mise run check`, documentation checker, and mdBook
  build after review fixes stabilize.

## Implementation Decomposition

1. `dstack-mol-v8c.1`: restore native Harper behavior and direct hook fixtures.
2. `dstack-mol-v8c.2`: replace redundant custom steps and remove non-semantic dependencies without losing checks.
3. `dstack-mol-v8c.3`: validate representative generated policies and reconcile exact documentation.

## Dependencies and Parallelism

This feature builds on delivered Language quality profiles. Tasks are serialized because the first two intentionally
modify the same root/template hk files and the final task validates their combined result. Every task depends directly
on specification reconciliation. Migration safety and clarity and Monorepo tooling layout depend on this feature.

## Rollout and Migration

Ship through the normal Copier update path. Existing projects reconcile local hk changes through three-way merge; the
migration feature separately prevents additive-adoption loss. No answer or lock schema migration is required.

## Risks and Tradeoffs

Removing artificial order can reveal a genuinely order-sensitive pair. Such a pair receives the smallest tested
exception rather than rebuilding the global chain. Native built-ins may change when hk is upgraded, but the synchronized
hk/Pkl pin bounds that behavior.

## Rejected Alternatives

- Keep the chain because it currently passes: rejected because it defeats hk's locking and obscures real dependencies.
- Remove all custom steps categorically: rejected because semantic docs checks and manifest guards are project-specific.
- Preserve the Harper ignore list: rejected because it disables expected lint categories and has no acceptance proof.
- Introduce generated Pkl fragments: rejected as unnecessary for the current direct conditional template.

## Open Questions

None.

## Deferred Decisions

A future hk version upgrade is separate maintenance and must rerun these behavioral fixtures.

## Planning Record

### Questions Asked and Answers

The user explicitly required native Harper linting, removal of unnecessary `depends`, use of standard config discovery,
and preservation rather than deletion of useful checks.

### Assumptions

hk 1.49's documented file-level locking remains the behavior of the currently pinned binary and Pkl package.

### Design Changes During Planning

The work was separated from migration safety so the template policy can stabilize before migration preservation tests
consume it.

### Source Material

Current root/generated hk policies and tests; hk 1.49 configuration, hook, built-in Rumdl, and Harper sources; the
user's migration and hook observations.
