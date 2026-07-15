# Universal project tooling

## Delivery Summary

- Beads feature root: `dstack-mol-lg3`
- Status: delivered
- Pull request: not created
- Merge commit: `abdf2f78ae6ee11389778fc66ce5ba6e430a8a9b` (fast-forward)
- Design record: [design.md](design.md)

## Delivered Capability

Every generated project now receives one mise-managed developer interface, one hk quality policy, concrete tooling
documentation, and a project-owned lock for Linux and macOS on x64 and ARM64.

## User-Facing Behavior

Contributors use `mise run check`, `mise run fix`, `mise run docs:check`, `mise run docs:build`, and
`mise run docs:serve`. Setup resolves `mise.lock`, installs tools with the lock enforced, and installs repository-local
hk hooks as a separate stage. Conflict-free Copier updates reconcile the same lock, tools, and hooks.

Provisioning failures preserve the rendered scaffold. Setup and update report separate mise availability, lock, install,
and hook states with bounded error text and exact recovery commands. Copier conflicts skip all newly rendered project
code until the user resolves and accounts for the update.

## Design Integration

Copier remains a local renderer; the generated stdlib provisioner owns network-backed tooling state. Provisioning
ignores user-global mise tools so the committed lock represents only the seven project tools. One serialized hk step map
powers read-only checks, explicit fixes, and pre-commit fixes with Git stashing. Language quality profiles can extend
this baseline with language profiles, and GitHub validation and docs deployment can consume its stable task names.

## Operational Impact

The initial lock targets `linux-x64`, `linux-arm64`, `macos-x64`, and `macos-arm64`. Setup without Git completes lock
and installation while reporting hooks as `skipped-no-git`. Explicit post-setup skipping executes no generated code.
Manual recovery uses `python3 scripts/setup-tooling.py --json` and the additional commands returned in
`tooling.recovery`.

## Reference and Contracts

- [Workflow architecture](../../architecture/index.md)
- [Install and use dstack](../../operations/index.md)
- [Developing dstack](../../development/index.md)
- [Repository and command reference](../../reference/index.md)

## Validation Evidence

- `uv run pytest -m "not external"`: 149 tests passed; 1 tag-only test skipped and 2 external tests deselected.
- `uv run pytest -q tests/test_repository.py::test_generated_tooling_contract_end_to_end`: 1 live generated-tooling
  contract test passed.
- `mise run check`: passed, including repository quality checks, documentation validation, and mdBook build.
- Live generated-project validation resolved and installed the four-platform lock, loaded tasks/hk config, executed the
  installed pre-commit hook while preserving unstaged work, applied explicit fixes, built docs, and ended clean.
- Setup/update simulations passed for missing mise, process-launch errors, lock/install/hook failures, no Git, explicit
  skip, stale locks, Copier conflicts, invalid provisioner output, and missing/empty locks.
- Every bounded implementation review and follow-up verification passed.

## Design Reconciliation

### Delivered as Designed

The exact seven-tool baseline, synchronized hk/Pkl pin, five stable tasks, four-platform lock, separate provisioning
stages, generated tooling pages, setup/update ownership, failure recovery, and root reader documentation match the
reviewed design.

### Intentional Changes

Implementation serialized every file-mutating hk step after a review exposed concurrent staging races. The provisioner
also isolates user-global mise configuration after live validation showed global tools could incorrectly participate in
a project lock/install. External validation now bootstraps mise without pre-installing project tools so the live test
proves the generated contract.

### Deferred Work

Language-specific profiles remain Language quality profiles. Generated GitHub validation and documentation deployment
remain GitHub validation and docs deployment. Monorepo layout remains Monorepo tooling layout.

### Rejected or Removed Scope

Generated projects do not receive application source, package manifests, dstack's release task, language-specific
checks, generated CI workflows, or Windows support from this feature.

### Adjacent Tracked Improvement

Implementation exposed an opportunity to reduce redundant full-suite runs. Separate task `dstack-pyn`, discovered from
Universal project tooling update task `dstack-mol-b69.5`, owns the resulting repository, canonical skill, and
generated-agent guidance. It was validated and closed in `5ec5176126e570ca37866f33237d67dd922b6bda`; it is recorded here
because that independently tracked commit is delivered on the same branch, not because it expands Universal project
tooling's product scope.

## Documentation Updated

- `docs/src/architecture/index.md`
- `docs/src/operations/index.md`
- `docs/src/development/index.md`
- `docs/src/reference/index.md`
- `docs/src/planned-features.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`
- `docs/src/features/universal-project-tooling/index.md`
- Generated `docs/src/development/tooling.md`
- Generated `docs/src/reference/tooling.md`
- Generated `README.md`

## Audit Trail

- Reviewed design and graph: `2f0f2cabc4080fde048e50bbfd9c4de4ed7f6a31`; roadmap readiness: `c299b69`.
- Universal templates (`dstack-mol-b69.1`): `9f4f3cd54542e0acf55127d26db26868de8f0626`.
- Setup provisioning (`dstack-mol-b69.2`): `46544538c1f0340e276a6a1ad4c88d81bde2d9f4`.
- Copier update reconciliation (`dstack-mol-b69.5`): `d2f3f4c1985ac12018eebc9e506de5dcceb28ab0`.
- End-to-end contract (`dstack-mol-b69.3`): `8a27aaf4c41ddf99ae68e3df0a32de4fed56d720`.
- Root reader documentation (`dstack-mol-b69.4`): `5646c163ef43e8c39c3b24996fafd3a35e94bef4`.
- Focused iterative validation guidance (`dstack-pyn`): `5ec5176126e570ca37866f33237d67dd922b6bda`.
- Implementation coordinator `dstack-mol-b69` closed after all five required children and acceptance checks completed.
