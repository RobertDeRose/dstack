# F030 — Language quality profiles

## Delivery Summary

- Beads feature root: `dstack-mol-ni2`
- Status: delivered
- Pull request: not created
- Merge commit: `0c30513c4321e135a1a81ae6c57e17b68770f59d` (fast-forward)
- Design record: [design.md](design.md)

## Delivered Capability

Generated projects can select Python, TypeScript, Rust, Go, Elixir, and Nix quality profiles, combine recognized
profiles for one polyglot root policy, or select exclusive `other` for only the universal tooling baseline. Setup and
updates record the canonical selection without generating application manifests, dependencies, package roots, or source.

## User-Facing Behavior

Setup accepts repeatable `--language-profile`; updates preserve the recorded selection unless repeatable `--add-profile`
or `--remove-profile` operations explicitly change it. Legacy updates inspect only root manifests and present
suggestions for confirmation rather than applying them automatically.

Selected profiles extend the existing five mise tasks and one hk policy with file-gated source checks and fixes.
Root-manifest-gated project checks run only when relevant. Pytest, Vitest, and Credo remain project-owned dependencies;
flake checks require system Nix. Missing prerequisites fail with profile-specific messages.

## Design Integration

F030 composes direct membership-gated sections into F020's `mise.toml`, `hk.pkl`, ignores, provisioner, and generated
tooling pages. Mutating source steps are serialized in canonical profile order. Check-only project steps stay out of fix
and pre-commit, except the explicit Go module-tidy fix. Profiles add no task names or second provisioning path.

## Operational Impact

The universal lock still targets Linux and macOS on x64 and ARM64. Nixfmt-rs is supported on Linux x64/ARM64 and macOS
ARM64. The provisioner validates those entries and atomically removes only nixfmt-rs's macOS x64 lock table before
locked installation. Matching Nix inputs fail clearly on unsupported macOS x64. Profile source and project checks skip
cleanly when their files or root manifests are absent.

## Reference and Contracts

- [Workflow architecture](../../architecture/index.md)
- [Install and use dstack](../../operations/index.md)
- [Developing dstack](../../development/index.md)
- [Repository and command reference](../../reference/index.md)

## Validation Evidence

- `uv run --frozen --group test pytest -q`: 163 tests passed; 1 tag-only release test skipped.
- `uv run pytest -q tests/test_repository.py -k "language_profile"`: exhaustive selection and profile contract checks
  passed.
- `uv run pytest -q tests/test_repository.py::test_generated_language_profiles_end_to_end`: the real combined
  four-platform lock, locked install, and all profile source fix/check steps passed.
- `mise run check`: passed, including repository quality checks, documentation validation, and mdBook build.
- `uv run scripts/check-docs.py`, `mdbook build docs`, and `git diff --check`: passed.
- Every bounded implementation review and targeted follow-up verification passed.

## Design Reconciliation

### Delivered as Designed

Canonical selection, explicit setup/update operations, root-only legacy suggestions, all six recognized profiles,
exclusive `other`, manifest-gated project checks, project-owned ecosystem dependencies, stable tasks, conditional
ignores and documentation, and the no-application-scaffolding boundary match the reviewed design.

### Intentional Changes

Mise's `os` selector filters installation on the current host but does not filter cross-platform lock resolution. Mise
2026.7.5 resolved a wasm fallback for nixfmt-rs on macOS x64. The generated provisioner therefore validates the three
supported nixfmt-rs entries and atomically removes only its macOS x64 table while retaining the four-platform lock for
all other tools.

### Deferred Work

Generated GitHub validation and documentation deployment remain F040. Package-local policy and monorepo layout remain
F050.

### Rejected or Removed Scope

Profiles do not generate or modify package manifests, dependencies, application source, package roots, CI workflows,
release automation, or monorepo structure. `other` adds no executable language behavior.

## Documentation Updated

- `docs/src/architecture/index.md`
- `docs/src/operations/index.md`
- `docs/src/development/index.md`
- `docs/src/reference/index.md`
- `docs/src/planned-features.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`
- `docs/src/features/030-language-quality-profiles/index.md`
- Generated `docs/src/development/tooling.md`
- Generated `docs/src/reference/tooling.md`

## Audit Trail

- Reviewed design and execution graph: `7b128d03bbab008986b3d2be09823902a76b0709`; implementation readiness:
  `d61441de372f81400d79791baf8b8d513ec5ce04`.
- Profile composition and setup/update selection (`dstack-mol-9as.1`): `40936dccd29e66d73cc94b9ca177493a077fa2fc`.
- Python and TypeScript profiles (`dstack-mol-9as.2`): `b6e0a8d183b4642cf16bd65df970a54c0b4d3944`.
- Rust and Go profiles (`dstack-mol-9as.3`): `63aae1c7d93aef5683b76e547a98e2c05099cb38`.
- Elixir and Nix profiles (`dstack-mol-9as.5`): `2586cc536ce8c95d70a5fd32d68cfe8d86436b37`.
- Exhaustive matrix, real combined contract, and final documentation (`dstack-mol-9as.4`):
  `762f8515667b0d198681ad7d698def25f6596001`.
- Implementation coordinator `dstack-mol-9as` closed after every required child passed acceptance and fresh review.
