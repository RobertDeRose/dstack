# F020 — Universal project tooling

## Delivery Summary

- Beads feature root: `dstack-mol-lg3`
- Status: ready for delivery
- Pull request: not created
- Merge commit: not merged
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
powers read-only checks, explicit fixes, and pre-commit fixes with Git stashing. F030 can extend this baseline with
language profiles, and F040 can consume its stable task names.

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

Language-specific profiles remain F030. Generated GitHub validation and documentation deployment remain F040. Monorepo
layout remains F050.

### Rejected or Removed Scope

Generated projects do not receive application source, package manifests, dstack's release task, language-specific
checks, generated CI workflows, or Windows support from this feature.

### Adjacent Tracked Improvement

Implementation exposed an opportunity to reduce redundant full-suite runs. Separate task `dstack-pyn`, discovered from
F020 update task `dstack-mol-b69.5`, owns the resulting repository, canonical skill, and generated-agent guidance. It
was validated and closed in `a9dbee27687ace743cd8513bb261a90e42bded80`; it is recorded here because that independently
tracked commit is delivered on the same branch, not because it expands F020's product scope.

## Documentation Updated

- `docs/src/architecture/index.md`
- `docs/src/operations/index.md`
- `docs/src/development/index.md`
- `docs/src/reference/index.md`
- `docs/src/planned-features.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`
- `docs/src/features/020-universal-project-tooling/index.md`
- Generated `docs/src/development/tooling.md`
- Generated `docs/src/reference/tooling.md`
- Generated `README.md`

## Audit Trail

- Reviewed design and graph: `18083884a63b4b38e19cbc9dedbc256935e038fc`; roadmap readiness: `90670b8`.
- Universal templates (`dstack-mol-b69.1`): `8c7c71fdb98e58c0616494cbf8e1cfd7a5cb19af`.
- Setup provisioning (`dstack-mol-b69.2`): `e873591c0f990d7c0e84eecbe9a111286f9cf19f`.
- Copier update reconciliation (`dstack-mol-b69.5`): `203bc0fb87beb38f71b34a4767a294522dbff06b`.
- End-to-end contract (`dstack-mol-b69.3`): `8eba38469bebe821f5c74db0f3907426787f07d2`.
- Root reader documentation (`dstack-mol-b69.4`): `27ff9dac4290270260f8bd8b6b1f2e223489faa7`.
- Focused iterative validation guidance (`dstack-pyn`): `a9dbee27687ace743cd8513bb261a90e42bded80`.
- Implementation coordinator `dstack-mol-b69` closed after all five required children and acceptance checks completed.
