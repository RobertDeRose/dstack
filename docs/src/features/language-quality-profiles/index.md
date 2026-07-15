# Language quality profiles

## Delivery Summary

- Beads feature root: `dstack-mol-ni2`
- Status: delivered
- Pull request: not created
- Merge commit: `1e8199c367d390bde7d39103def8162e32388d74` (fast-forward)
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

Language quality profiles composes direct membership-gated sections into Universal project tooling's `mise.toml`,
`hk.pkl`, ignores, provisioner, and generated tooling pages. Mutating source steps are serialized in canonical profile
order. Check-only project steps stay out of fix and pre-commit, except the explicit Go module-tidy fix. Profiles add no
task names or second provisioning path.

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

Generated GitHub validation and documentation deployment remain GitHub validation and docs deployment. Package-local
policy and monorepo layout remain Monorepo tooling layout.

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
- `docs/src/features/language-quality-profiles/index.md`
- Generated `docs/src/development/tooling.md`
- Generated `docs/src/reference/tooling.md`

## Audit Trail

- Reviewed design and execution graph: `5ca8fd8f6bb26917922ac37616f2fcd0591104af`; implementation readiness:
  `d5d39e61b362c206717070e3e28cc28c39e3ad66`.
- Profile composition and setup/update selection (`dstack-mol-9as.1`): `9f98e1075d17f960cf8e19fda78a05aa960a6026`.
- Python and TypeScript profiles (`dstack-mol-9as.2`): `5b58d3ea5b99f183f7caa5cc737a46341df6daef`.
- Rust and Go profiles (`dstack-mol-9as.3`): `315fffd860c12b8a58c6a4eab9da52f158bb1946`.
- Elixir and Nix profiles (`dstack-mol-9as.5`): `9619844b4a12ce7b02fd996a77ceb149b45d605f`.
- Exhaustive matrix, real combined contract, and final documentation (`dstack-mol-9as.4`):
  `032c2b5fb8044bf0e0b962412a3dd8bc8fe5fa6c`.
- Implementation coordinator `dstack-mol-9as` closed after every required child passed acceptance and fresh review.
