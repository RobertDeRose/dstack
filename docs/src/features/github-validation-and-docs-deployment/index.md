# GitHub validation and docs deployment

## Delivery Summary

- Beads feature root: `dstack-mol-8fe`
- Status: delivered
- Pull request: not created
- Merge commit: `6f5965513307f9560ebe5fc281cc72d10e918e2a` (fast-forward)
- Design record: [design.md](design.md)

## Delivered Capability

Every generated project receives GitHub validation that installs the committed mise lock and invokes the same local
`mise run check` policy. Generated mdBook documentation can be published through an opt-in GitHub Pages workflow after
an administrator explicitly enables repository state through external GitHub CLI.

## User-Facing Behavior

`.github/workflows/validate.yml` runs on pushes and pull requests with only `contents: read`, disables automatic mise
installation and checkout credential persistence, isolates user-global mise configuration, installs with
`mise install --locked`, and runs only `mise run check`.

`.github/workflows/docs.yml` accepts only configured-default-branch pushes and manual dispatches. Both jobs require
`DOCS_DEPLOYMENT_ENABLED == 'true'`. The build job receives only `contents: read`, installs locked tools, runs
`mise run docs:build`, and uploads `docs/book`; the deploy job alone receives `pages: write` and `id-token: write` and
targets the `github-pages` environment.

Administrators run `mise run docs:deployment:enable` with an external authenticated `gh`. The idempotent helper creates
or updates Pages with `build_type=workflow`, sets the repository variable only after Pages configuration succeeds, and
prints the Pages URL. Failures stop without claiming success and include exact manual recovery commands.

## Design Integration

GitHub validation and docs deployment reuses Universal project tooling's committed lock, named tasks, hk policy, and
generated documentation. It adds no second CI quality policy and does not add `gh` to the nine universal mise tools.
Copier renders repository files but never changes GitHub state; only the explicit administrator task crosses that
boundary. Language quality profiles profiles compose underneath the same workflows without changing their triggers,
permissions, or commands.

## Operational Impact

Pages remains disabled after setup and Copier update. Deployment requires both repository-side `build_type=workflow` and
the exact true repository variable. Pull requests and forks have no deployment path. Repeating the enable task converges
on the same state. Missing `gh`, authentication, repository resolution, API access, variable permission, or URL lookup
produces a nonzero result with installation or manual recovery guidance.

## Reference and Contracts

- [Workflow architecture](../../architecture/index.md)
- [Install and use dstack](../../operations/index.md)
- [Developing dstack](../../development/index.md)
- [Repository and command reference](../../reference/index.md)

## Validation Evidence

- `uv run --frozen --group test pytest -q`: 189 tests passed; 1 tag-only release test skipped.
- `mise run check`: passed, including repository quality checks, documentation validation, and mdBook build.
- Focused validation, deployment, and enablement tests passed through both Copier entry points.
- Rendered workflows passed actionlint and zizmor; combined profile and conflict-free Copier update coverage passed.
- Every bounded implementation review and targeted follow-up verification passed.
- Credentialed disposable-repository exercise (`mise run docs:deployment:enable` twice, then verify Pages
  `build_type=workflow`, `DOCS_DEPLOYMENT_ENABLED`, and `html_url`): waived by the user for commit
  `1ceb5db0da0665b86aabfafbe0df72d929882ccd`. Residual risk: mocked coverage cannot prove current GitHub API,
  permission, or Pages-provisioning behavior against a live repository.

## Design Reconciliation

### Delivered as Designed

Locked local/CI parity, full action pins, least-privilege job permissions, default-branch-only Pages deployment, exact
repository gating, external-`gh` administration, safe mutation ordering, nine tools, six tasks, standalone generated
operations documentation, both Copier entry points, and conflict-free updates match the reviewed design.

### Intentional Changes

Implementation tasks were serialized after preflight confirmed that every generated file and task changes shared exact
scaffold assertions. Default-branch interpolation uses YAML-safe JSON quoting. The Pages build disables mise caching to
avoid runtime-artifact cache poisoning. Enablement recognizes only a terminal `(HTTP 404)` as absent Pages and publishes
exact fallback commands on every failure.

### Deferred Work

Package-local tooling and monorepo layout remain Monorepo tooling layout. No GitHub validation and docs deployment
product scope is deferred.

### Rejected or Removed Scope

GitHub validation and docs deployment does not add raw duplicate linter commands, lock regeneration, pull-request
deployment, path-filtered deployment, universal `gh` installation, automatic GitHub mutation during setup/update,
application deployment, release automation, or package manifests.

## Documentation Updated

- `docs/src/architecture/index.md`
- `docs/src/operations/index.md`
- `docs/src/development/index.md`
- `docs/src/reference/index.md`
- `docs/src/planned-features.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`
- `docs/src/features/github-validation-and-docs-deployment/index.md`
- Generated `docs/src/development/tooling.md`
- Generated `docs/src/operations/github-pages.md`
- Generated `docs/src/reference/tooling.md`

## Audit Trail

- Reviewed design and execution graph: `35e4f79eae2a7dee06fb3cbe83d82905e8927e96`; serialized task correction:
  `2d68e33143c8b8d5cbc9e04ce005288a91ced78f`.
- Locked GitHub validation (`dstack-mol-41q.1`): `daf79c92331b4bd06f4b623f43d7acb5d44dbd75`.
- Gated Pages deployment (`dstack-mol-41q.2`): `6ed08b2e4ea908e37a7d56a102d5102775de2e39`.
- Safe external-`gh` enablement (`dstack-mol-41q.3`): `4018b63047972f8b951c396d01ffe00a843eb7a8`.
- Combined profile/update integration (`dstack-mol-41q.4`): `1ceb5db0da0665b86aabfafbe0df72d929882ccd`.
- Implementation coordinator `dstack-mol-41q` closed after every required child passed acceptance and fresh review.
- Holistic delivery and drift reviews passed after reconciling the waiver, lifecycle status, and manual-dispatch
  wording.
