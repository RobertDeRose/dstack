# Design — F020 Universal project tooling

## Metadata

- Beads feature root: `dstack-mol-lg3`
- Feature number: `020`
- Feature slug: `universal-project-tooling`
- Design path: `docs/src/features/020-universal-project-tooling/design.md`
- Implemented record: `docs/src/features/020-universal-project-tooling/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Always generate a mise-managed developer interface and hk quality baseline, including documentation tasks, safe hooks,
and a resolved `mise.lock`.

## User Intent

Every dstack project should start with the same discoverable local/CI quality contract instead of assuming globally
installed tools.

## Goals

- Always render `mise.toml`, `hk.pkl`, supporting lint configuration, and universal ignores.
- Expose stable `check`, `fix`, `docs:check`, `docs:build`, and `docs:serve` tasks.
- Install hooks through mise and protect unstaged work during pre-commit fixes.
- Use `latest`, `stable`, and `lts` aliases to reduce template maintenance, then resolve each new project into
  `mise.lock`.
- Report tool setup as outstanding rather than destroy an otherwise valid scaffold when mise or downloads are
  unavailable.

## Non-Goals

- Add application source, package manifests, release automation, or language-specific checks.
- Copy dstack's semantic-release task into generated projects.
- Require global hk installation.

## User-Facing Behavior

After setup, `mise install` has run when possible, hooks execute through `mise x`, and contributors use named mise tasks
rather than raw tool commands. The generated lockfile makes each project deterministic after initial resolution.

## Requirements

### Functional Requirements

- Universal mise tools cover hk, mdBook, Markdown formatting/linting, typo checks, and every executable referenced by
  hk.
- `HK_MISE=1` and post-install `hk install --mise` are configured.
- The same hk step mapping powers safe pre-commit fixes, read-only checks, and explicit fixes.
- Universal hk checks cover conflicts, private keys, BOM/newlines, whitespace, executable/shebang consistency, Markdown,
  typos, and `scripts/check-docs.py`.
- Setup attempts `mise install`, verifies/creates `mise.lock`, and reports structured status.

### Quality Requirements

- No hk step references an undeclared tool or missing config.
- `mise tasks` is self-documenting.
- Fix steps are deterministic and use Git stashing.
- Generated docs build with the locked toolchain.

### Compatibility and Migration Requirements

This is a pre-1.0 template change. Copier updates may introduce the baseline into existing managed projects, with normal
three-way conflict review.

## Existing Context

dstack itself now uses mise, hk, mdBook tasks, and documentation validation. The current generated template has none of
these despite advertising `uv` and mdBook commands.

## Proposed Design

Render a small shared `mise.toml` and `hk.pkl`; keep substantial task scripts external only when needed. Use aliases in
template source and run mise during post-setup to resolve the project lock. Return tooling availability, install, lock,
and hook results separately from documentation/Beads status.

## Architecture Consistency

### Existing Patterns Reused

The shared linter mapping and check/fix/pre-commit hooks used by all three surveyed repositories and dstack itself.

### Invariants Preserved

Template rendering remains safe and local. Tool downloads are post-render effects with explicit status, not
template-source retrieval.

### New Decisions Introduced

Universal developer tooling is mandatory; resolved lock state, not template pin churn, provides per-project determinism.

### Architecture Documentation Changes

Update the workflow architecture with the mise → hk → docs validation path.

## Operational Considerations

Offline setup completes with tooling marked outstanding. Rerunning `mise install` completes provisioning. Hook
installation errors are visible rather than silently ignored.

## Documentation Impact

| Documentation concern      | Exact page                                                 | Create or update           | Planned change                      | Owning Beads task   |
|----------------------------|------------------------------------------------------------|----------------------------|-------------------------------------|---------------------|
| Architecture               | `docs/src/architecture/index.md`                           | Update                     | Tool authority and validation flow  | F020 docs           |
| Usage                      | `docs/src/operations/index.md`                             | Update                     | Setup outcomes and recovery         | F020 docs           |
| Development                | `docs/src/development/index.md`                            | Update                     | Canonical tasks and hook behavior   | F020 docs           |
| Reference                  | `docs/src/reference/index.md`                              | Update                     | Generated files/tasks/status fields | F020 docs           |
| Navigation                 | `docs/src/SUMMARY.md`                                      | Update only if pages added | Keep links current                  | F020 docs           |
| Implemented Feature Record | `docs/src/features/020-universal-project-tooling/index.md` | Create during close-out    | Delivery evidence                   | lifecycle close-out |

## Validation Strategy

Render a project, run mise install/tasks/check/fix/docs build, verify lock presence and hook config, simulate missing
mise and failed download paths, and run repository tests plus `git diff --check`.

## Implementation Decomposition

1. Add common mise/hk/config templates.
2. Add post-render mise installation and structured outcomes.
3. Add generated-project end-to-end validation.
4. Document the developer contract.

## Dependencies and Parallelism

Independent of F010 at the config level; generated docs text should reconcile with F010 if both land concurrently.

## Rollout and Migration

Land before language profiles and CI so both can extend one stable baseline.

## Risks and Tradeoffs

Aliases make initial resolution network-dependent, but reduce template maintenance and the committed lock restores
determinism afterward.

## Rejected Alternatives

- Explicit template pins: rejected to reduce maintenance.
- Optional baseline: rejected; every generated project should have one command contract.
- Independent CI scripts: rejected to prevent local/CI drift.

## Open Questions

None.

## Deferred Decisions

Project release automation remains project-owned.

## Planning Record

### Questions Asked and Answers

The user required universal inclusion, alias-based versions, a committed lock, and best-effort setup installation.

### Assumptions

`mise lock` or installation produces the supported lock artifact for the installed mise release.

### Design Changes During Planning

The earlier explicit-pin recommendation was rejected in favor of aliases plus `mise.lock`.

### Source Material

Official hk mise integration documentation and the AtomixOS, Nixstasis, Conduit, and dstack configurations.
