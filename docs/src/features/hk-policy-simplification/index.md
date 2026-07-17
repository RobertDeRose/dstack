# hk policy simplification

## Delivery Summary

- Beads feature root: `dstack-mol-5v0`
- Status: close-out in progress
- Delivery action: merge requested
- Pull request: not created
- Merge commit: pending close-out and fast-forward delivery
- Design record: [design.md](design.md)

## Delivered Capability

Root and generated projects use a smaller native-first hk policy. Equivalent formatter and linter commands use pinned hk
built-ins, and independent checks rely on native file locking. Go alone retains output-sensitive dependencies so final
source and module metadata agree.

Commit-message hooks now apply Harper's full native rule set to human-authored content while preserving exact Git
metadata, canonical Beads footers, and stable release subjects.

## User-Facing Behavior

`mise run check`, `mise run fix`, pre-commit, and commit-message hooks retain their supported validation inventory.
Custom steps remain only where native behavior is not equivalent. Generated language profiles compose without a broad
serialization chain. `gofumpt` runs after `goimports`, and fix-only module tidy runs after both source formatters.

## Design Integration

The policy preserves the universal-tooling and language-profile contracts. Root and Copier-generated Pkl remain aligned,
while project-specific Contextlint, documentation, Markdown-table, Rumdl, language, and manifest gates keep documented
custom implementations. File locks, rather than unrelated dependency edges, coordinate concurrent fixes.

## Operational Impact

No deployment or runtime operations change. Contributors keep using the existing mise commands and installed Git hooks.
Hook stashing restores unrelated unstaged content byte for byte.

## Reference and Contracts

- [Workflow architecture](../../architecture/index.md)
- [Developing dstack](../../development/index.md)
- [Developer tooling](../../development/tooling.md)
- [Repository and command reference](../../reference/index.md)
- [Generated tooling contract](../../reference/tooling.md)

## Validation Evidence

- Static repository partition: 127 passed, 1 skipped.
- Repository integration partition: 59 passed.
- Additional deployment, enablement, validation, and migration integration partition: 22 passed.
- Baseline and six language-profile focused tests: 7 passed.
- Generated tooling end-to-end external test passed, including hook behavior, fix-to-check convergence, and exact
  unstaged-byte restoration.
- `HK_JOBS=1 mise run check`, `uv run scripts/check-docs.py`, Pkl evaluation, mdBook, and `git diff --check` passed.
- Every implementation task received an independent review and passed its follow-up review.

## Design Reconciliation

### Delivered as Designed

Native built-ins replace equivalent custom steps, Harper keeps its full rule set, Git and Beads metadata filtering is
narrow, supported checks remain present, and the broad dependency chain is removed.

### Intentional Changes

The exact stable `release: vX.Y.Z` subject is filtered on physical line one because the existing release contract is
authoritative. Release-shaped body text and prerelease subjects remain linted. Rumdl stays minimally custom because its
built-in diff header is incompatible with hk's canonicalization behavior.

### Deferred Work

Migration preservation and prompting belong to Migration safety and clarity. Package-local policy belongs to Monorepo
tooling layout.

### Rejected or Removed Scope

No validation capability was removed. Unrelated checks are not serialized merely to produce deterministic console order,
and Harper rule classes are not disabled to accommodate machine-authored metadata.

## Documentation Updated

- `docs/src/architecture/index.md`
- `docs/src/development/index.md`
- `docs/src/development/tooling.md`
- `docs/src/reference/index.md`
- `docs/src/reference/tooling.md`
- `docs/src/planned-features.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`
- `docs/src/features/hk-policy-simplification/index.md`
- Generated development and reference tooling templates

## Audit Trail

- Reviewed specification and execution graph: `b156f9418a8bc29bca96e37ca7fa63b4deed70e1`.
- Release-contract specification correction: `1b893379156828ceabe99b8fdc97a2acfeef3a42`.
- Native Harper restoration (`dstack-mol-v8c.1`): `13baa637767345bc37fe3562ecc7962c6222ab73`.
- Native-step and dependency simplification (`dstack-mol-v8c.2`): `3e6239b695e993c4322921db5f5509c098ed5fd9`.
- Final validation evidence (`dstack-mol-v8c.3`): `3eedbe50af0d0e20e450ba89fc62e5b5c915dbf4`.
- Implementation coordinator `dstack-mol-v8c` closed after all reviewed tasks passed acceptance.
