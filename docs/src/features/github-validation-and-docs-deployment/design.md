# Design — GitHub validation and docs deployment

## Metadata

- Beads feature root: `dstack-mol-8fe`
- Feature slug: `github-validation-and-docs-deployment`
- Design path: `docs/src/features/github-validation-and-docs-deployment/design.md`
- Implemented record: `docs/src/features/github-validation-and-docs-deployment/index.md`
- Base branch: `main`
- Status: reviewed

## Feature Summary

Generate GitHub Actions validation that reuses the locked mise/hk interface and a committed GitHub Pages workflow that
stays disabled until an explicit gh-backed operator task enables repository state.

## User Intent

Every generated GitHub project should have local/CI parity and an easy path to documentation deployment without failing
before Pages is configured.

## Goals

- Always generate validation that installs the committed mise lock and runs the same named check task used locally.
- Commit a Pages workflow whose build and deploy jobs are disabled by default.
- Provide `mise run docs:deployment:enable` to verify GitHub context/authentication, select workflow-based Pages builds,
  and set the enable variable last.
- Report the Pages URL or actionable recovery without rewriting generated source.

## Non-Goals

- Support non-GitHub CI or documentation hosting.
- Automatically create, publish, or choose a GitHub repository.
- Enable Pages without explicit operator invocation.
- Install or lock the GitHub CLI as a universal project tool.
- Deploy documentation from pull requests or non-default branches.

## User-Facing Behavior

Validation runs on every pull request and push. It performs an isolated `mise install --locked` and then only
`mise run check`; hk remains the single validation policy and already validates/builds documentation.

`.github/workflows/docs.yml` runs only for pushes to the rendered `repository_default_branch` and explicit
`workflow_dispatch`. Both build and deploy jobs require `vars.DOCS_DEPLOYMENT_ENABLED == 'true'`, so an absent variable
is false and no artifact or deployment occurs. The workflow builds with `mise run docs:build`, uploads `docs/book`, and
deploys to the `github-pages` environment.

`mise run docs:deployment:enable` treats `gh` as an external administrative prerequisite. It verifies the executable,
`gh auth status`, and repository context; creates or updates Pages to `build_type=workflow`; sets
`DOCS_DEPLOYMENT_ENABLED=true` only after Pages configuration succeeds; then prints the Pages URL. Repeated calls are
idempotent. Local tasks remain usable without `gh` or a GitHub remote.

## Requirements

### Functional Requirements

#### Validation workflow

Generate `.github/workflows/validate.yml` with:

- triggers `push` and `pull_request`, without write permissions;
- job-level `contents: read`;
- checkout with persisted credentials disabled;
- `jdx/mise-action` setup with automatic installation disabled;
- `MISE_GLOBAL_CONFIG_FILE=/dev/null mise install --locked`;
- `mise run check` as the sole validation command.

CI never runs `mise lock`, duplicates hk policy, or separately invokes mdBook.

#### Pages workflow

Generate `.github/workflows/docs.yml` with:

- `push.branches: [repository_default_branch]` rendered from Copier answers plus `workflow_dispatch`;
- no `pull_request` trigger and no path filter;
- concurrency group `pages` with `cancel-in-progress: false`;
- build job condition `vars.DOCS_DEPLOYMENT_ENABLED == 'true'`, `contents: read`, locked mise installation,
  `mise run docs:build`, Pages configuration, and upload of `docs/book`;
- deploy job depending on build, carrying the same gate, only `pages: write` and `id-token: write`, and
  `environment.name: github-pages` with its URL from the deploy action output.

Fork pull requests therefore receive neither Pages permissions nor a deployment path.

#### Enable task

Add the sixth generated mise task, `docs:deployment:enable`, backed by a generated stdlib helper. The helper performs,
in order:

1. find `gh`, otherwise print installation guidance and the manual commands below;
2. run `gh auth status`;
3. resolve `OWNER/REPO` with `gh repo view --json nameWithOwner --jq .nameWithOwner`;
4. query `GET /repos/{owner}/{repo}/pages`;
5. on HTTP 404, create Pages with `POST /repos/{owner}/{repo}/pages -f build_type=workflow`; otherwise update it with
   `PUT /repos/{owner}/{repo}/pages -f build_type=workflow`; any other GET/API failure stops;
6. set `DOCS_DEPLOYMENT_ENABLED=true` with `gh variable set` only after Pages configuration succeeds;
7. query Pages again and print `.html_url`.

A Pages change followed by variable failure remains safe because deployment stays disabled. Repetition converges on the
same Pages build type and variable. The helper returns nonzero and never claims success on authentication, repository,
API, or variable failures.

Manual fallback is:

```bash
gh api --method PUT repos/OWNER/REPO/pages -f build_type=workflow
gh variable set DOCS_DEPLOYMENT_ENABLED --body true --repo OWNER/REPO
```

For a repository without an existing Pages site, use POST instead of PUT for the first command.

### Action Pin Contract

Generated workflows pin actions to these full commits, with comments naming their major tags:

| Action                          | Major | Commit                                     |
|---------------------------------|-------|--------------------------------------------|
| `actions/checkout`              | `v6`  | `df4cb1c069e1874edd31b4311f1884172cec0e10` |
| `jdx/mise-action`               | `v3`  | `5228313ee0372e111a38da051671ca30fc5a96db` |
| `actions/configure-pages`       | `v5`  | `983d7736d9b0ae728b81ab479565c72886d7745b` |
| `actions/upload-pages-artifact` | `v4`  | `7b1f4a764d45c48632c6b24a0339c27f5614fb0b` |
| `actions/deploy-pages`          | `v4`  | `d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e` |

### Quality Requirements

- Actionlint and zizmor validate both rendered workflows.
- Static tests assert exact triggers, branch, gates, permissions, environment, artifact path, action pins, and commands.
- Pull requests from forks cannot obtain deployment permissions.
- The enable helper passes deterministic mocked success, repeat, missing-gh, auth, missing-remote, 404-create, non-404
  API, variable, and final-query cases.
- Both Copier entry points and conflict-free updates render/preserve the workflows, sixth task, helper, and docs.

### Compatibility and Migration Requirements

Existing managed projects receive workflows, task, helper, and docs through Copier update. Repository variables and
Pages settings remain GitHub-owned state and are never reset by Copier. Conflicts continue to block generated-code
execution. Projects without GitHub or `gh` retain the existing local tasks and receive clear enablement guidance.

## Existing Context

Purposeful project scaffold provides factual docs to publish. Universal project tooling provides one locked mise/hk
interface and five stable contributor tasks. Language quality profiles composes language profiles without adding CI.
Root repository workflows demonstrate pinned Actions, read-only validation, and `install: false`, but generated
workflows remain separately specified product behavior.

## Proposed Design

Add two unconditional workflow templates, one generated stdlib enable helper, one mise operator task, one generated
operations page, and updates to existing generated tooling/reference pages. Validation consumes the five stable
Universal project tooling tasks without adding policy. GitHub validation and docs deployment intentionally extends the
shared mise interface from five to six tasks while retaining nine universal tools because `gh` is external.

## Architecture Consistency

### Existing Patterns Reused

- Universal project tooling locked installation and named tasks remain the CI authority.
- Copier only renders files; it does not mutate GitHub repository state.
- The explicit operator task owns the authenticated GitHub mutation.
- Validation and deployment remain separate workflows with separate permissions.

### Invariants Preserved

- CI does not regenerate locks or define a second validation policy.
- Missing credentials, remotes, Pages state, or external `gh` never break local development.
- Deployment permission exists only in the gated deployment job.
- GitHub state is changed only by explicit user invocation.

### New Decisions Introduced

- GitHub Actions is the generated CI provider.
- Feature designs and generated operations documentation remain published mdBook chapters.
- The generated task set becomes six; the universal tool set remains nine.
- `DOCS_DEPLOYMENT_ENABLED` and Pages `build_type=workflow` jointly gate delivery.

### Architecture Documentation Changes

Document CI parity, GitHub-state ownership, deployment permissions, gating, and the external-gh trust boundary in
`docs/src/architecture/index.md`.

## Operational Considerations

Enablement requires an authenticated `gh` identity with repository administration permission. The helper reports the
failed operation and manual fallback. The credentialed disposable-repository exercise belongs to lifecycle validation,
not an implementation child; if unavailable, validation records it as unavailable and remains blocked unless explicitly
waived.

## Documentation Impact

| Documentation concern | Exact page                                                                | Owner               | Planned change                                                  |
|-----------------------|---------------------------------------------------------------------------|---------------------|-----------------------------------------------------------------|
| Root architecture     | `docs/src/architecture/index.md`                                          | deployment task     | CI/deployment/GitHub-state trust boundaries                     |
| Root usage            | `docs/src/operations/index.md`                                            | enable task         | Enablement, recovery, manual fallback                           |
| Root development      | `docs/src/development/index.md`                                           | validation task     | Exact local/CI parity                                           |
| Root reference        | `docs/src/reference/index.md`                                             | enable task         | Workflows, task, variable, permissions, helper result           |
| Generated development | `skills/setup-project/template/docs/src/development/tooling.md.jinja`     | validation task     | CI parity and workflow paths                                    |
| Generated operations  | `skills/setup-project/template/docs/src/operations/github-pages.md.jinja` | enable task         | Enablement, recovery, fallback, URL                             |
| Generated reference   | `skills/setup-project/template/docs/src/reference/tooling.md.jinja`       | enable task         | Sixth task, variable, workflow/permission contract, external gh |
| Generated navigation  | `skills/setup-project/template/docs/src/SUMMARY.md.jinja`                 | enable task         | Register GitHub Pages operations page                           |
| Roadmap               | `docs/src/planned-features.md`                                            | integration task    | Mark implementation readiness                                   |
| Implemented record    | `docs/src/features/github-validation-and-docs-deployment/index.md`        | lifecycle close-out | Delivery evidence                                               |

Every page has one implementation commit owner. No new root reader page is needed.

## Validation Strategy

### Structural and simulated validation

- Render representative project kinds/profiles through both Copier entry points.
- Parse workflows as YAML; run actionlint and zizmor on rendered workflows.
- Assert exact pins, events, rendered default branch, job gates, permissions, environment, artifact path, locked
  install, and named tasks.
- Assert tool count stays nine and task set becomes the existing five plus `docs:deployment:enable`.
- Run mocked helper cases without network credentials.
- Exercise conflict-free Copier update and verify project-owned workflow edits follow normal Copier conflict handling
  while repository variables remain out of template state.
- Run generated docs checker and mdBook with the operations page registered.

### Bounded external validation

In lifecycle validation, use a disposable GitHub repository to run the enable task twice, verify Pages
`build_type=workflow`, verify the variable, and capture the Pages URL. Do not perform this mutation from an
implementation agent or without explicit credentials/repository authority.

Repository-wide validation remains `uv run --frozen --group test pytest`, `mise run check`, docs checker, and mdBook.

## Implementation Decomposition

1. **Validation workflow (`dstack-mol-41q.1`)**: generate `.github/workflows/validate.yml`; own root/generated
   development docs, focused tests in `tests/test_github_validation.py`, and shared exact-scaffold assertions caused by
   this file.
2. **Deployment workflow (`dstack-mol-41q.2`)**: after task 1, generate `.github/workflows/docs.yml`; own root
   architecture docs, focused tests in `tests/test_github_deployment.py`, and its shared exact-scaffold assertion delta.
3. **Enablement (`dstack-mol-41q.3`)**: after task 2, add helper and sixth task; own root operations/reference,
   generated operations/reference/navigation, focused tests in `tests/test_github_enablement.py`, and shared task/file
   assertions.
4. **Integration (`dstack-mol-41q.4`)**: after the other three, own remaining combined/update coverage in
   `tests/test_repository.py`, both-entrypoint integration, workflows/tasks/docs, and roadmap reconciliation.

Each task directly depends on specification reconciliation. Tasks 1–3 are serialized because every generated file/task
changes shared exact-scaffold assertions that must pass at each task commit; task 4 is the final integration gate.

## Dependencies and Parallelism

Purposeful project scaffold and Universal project tooling are delivered prerequisites. Language quality profiles is
delivered context. After specification reconciliation, implementation proceeds validation → deployment → enablement →
integration.

## Rollout and Migration

Deployment remains disabled after setup/update unless the existing repository variable is exactly `true`. Adding or
updating generated files never invokes `gh`, changes Pages, or changes repository variables.

## Risks and Tradeoffs

- GitHub API or permission changes can break enablement; narrow calls and exact failure reporting limit ambiguity.
- `gh` is external, so enablement may require installation; this avoids four-platform lock/install cost for a one-time
  administration task.
- Workflow pins age; explicit full SHAs and comments allow audited updates.

## Rejected Alternatives

- Mise-managed `gh`: recurring four-platform lock/install cost for an occasional administrative task.
- Disabled filename: GitHub cannot discover it as a workflow.
- Workflow dispatch only: no automatic post-enable deployment.
- Source rewriting: dirty state and Copier conflicts.
- Deployment enabled by default: failures before Pages configuration.
- Variable first, Pages API second: could enable deployment before Pages is safely configured.

## Open Questions

None.

## Deferred Decisions

Other CI providers and documentation hosts remain consumer-driven future work.

## Planning Record

### Questions Asked and Answers

The user required validation, a disabled deployment workflow, and gh automation. They approved a repository-variable
gate and API-based Pages configuration. During specification review, the user chose external `gh` with preflight and
installation guidance rather than an eighth universally locked mise tool.

### Assumptions

Generated projects target GitHub even when the remote is added after setup. `repository_default_branch` is the only
automatic deployment branch. Explicit manual dispatch is useful for recovery but remains gated.

### Design Changes During Planning

- Deployment changed from optional generation to always-generated but disabled behavior.
- CI parity was narrowed to locked installation plus `mise run check`, avoiding duplicate mdBook work.
- Deployment trigger, permissions, environment, and artifact path became explicit.
- `gh` changed from proposed universal mise tooling to an external administrative prerequisite.
- Generated operations/development/reference documentation received exact ownership.
- Tasks 1–3 were initially separated, then serialized when implementation preflight confirmed each changes shared
  exact-scaffold assertions; task 4 remains the integration gate.

### Source Material

- Delivered Purposeful project scaffold/Universal project tooling/Language quality profiles records and current
  generated tooling contracts.
- Existing dstack validation workflows as repository patterns.
- GitHub Pages REST and custom workflow documentation: <https://docs.github.com/en/rest/pages/pages> and
  <https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages>.
- GitHub CLI manuals: <https://cli.github.com/manual/gh_api>, <https://cli.github.com/manual/gh_repo_view>, and
  <https://cli.github.com/manual/gh_variable_set>.
- Action tag commits verified from upstream Git refs on 2026-07-14.
