# Design — F040 GitHub validation and docs deployment

## Metadata

- Beads feature root: `dstack-mol-8fe`
- Feature number: `040`
- Feature slug: `github-validation-and-docs-deployment`
- Design path: `docs/src/features/040-github-validation-and-docs-deployment/design.md`
- Implemented record: `docs/src/features/040-github-validation-and-docs-deployment/index.md`
- Base branch: `main`
- Status: draft

## Feature Summary

Generate GitHub Actions validation that reuses mise/hk and a committed but gated Pages deployment workflow that a mise
task enables through `gh`.

## User Intent

Every generated GitHub project should have local/CI parity and an easy path to documentation deployment without failing
before Pages is configured.

## Goals

- Always generate validation for mise install, `hk check -a`, and mdBook build.
- Commit a docs deployment workflow whose deploy job is disabled by default.
- Provide a mise task that verifies gh authentication, switches Pages to GitHub Actions, and sets the enable variable.
- Avoid source-rewriting enable scripts.

## Non-Goals

- Support non-GitHub CI or documentation hosting in this feature.
- Automatically create or publish a GitHub repository.
- Enable Pages without an explicit task invocation.

## User-Facing Behavior

Validation runs on normal pull requests and pushes. Docs deployment remains gated on `DOCS_DEPLOYMENT_ENABLED=true`.
`mise run docs:deployment:enable` performs the explicit repository mutation and reports the Pages URL or actionable
failure.

## Requirements

### Functional Requirements

- The validation workflow invokes the same named tasks used locally.
- The deployment workflow builds the exact configured mdBook output and uses GitHub Pages actions with least-required
  permissions.
- The deploy job condition checks a repository variable and is false by default.
- The enable task checks repository context and `gh auth status`, calls the GitHub Pages API to select workflow builds,
  and sets the repository variable.
- Repeated enable calls are idempotent.

### Quality Requirements

- Actions are pinned according to repository policy.
- Pull requests from forks cannot gain deployment permissions.
- API and authentication failures do not partially claim success.
- Workflow YAML is validated by actionlint and zizmor.

### Compatibility and Migration Requirements

Generated projects without a GitHub remote retain functioning local tasks; the enable task exits with clear guidance.

## Existing Context

AtomixOS and Conduit successfully reuse local mise/hk commands in CI and deploy mdBook separately. F020 provides the
universal command surface; F010 provides meaningful docs to publish.

## Proposed Design

Generate one validation workflow and one Pages workflow. Gate deployment on a repository variable rather than renaming
or rewriting workflow files. Add `gh` to universal mise tooling and an explicit enable task that performs both required
GitHub settings mutations.

## Architecture Consistency

### Existing Patterns Reused

Stable mise tasks, shared hk policy, explicit trust-boundary mutation, and separated validation/deployment workflows.

### Invariants Preserved

Local configuration remains authoritative; CI does not define an independent validation policy.

### New Decisions Introduced

GitHub Actions is the generated CI provider. Documentation deployment is present but disabled through repository state.

### Architecture Documentation Changes

Document CI parity, Pages trust boundaries, permissions, and the enable flow.

## Operational Considerations

The enable task requires an authenticated gh identity with repository administration permission. It should print manual
API/settings instructions when automation is unavailable.

## Documentation Impact

| Documentation concern      | Exact page                                                             | Create or update                        | Planned change                        | Owning Beads task   |
|----------------------------|------------------------------------------------------------------------|-----------------------------------------|---------------------------------------|---------------------|
| Architecture               | `docs/src/architecture/index.md`                                       | Update                                  | CI/deployment boundaries              | F040 docs           |
| Usage                      | `docs/src/operations/index.md`                                         | Update                                  | Enable and troubleshoot deployment    | F040 docs           |
| Development                | `docs/src/development/index.md`                                        | Update                                  | Local/CI command parity               | F040 docs           |
| Reference                  | `docs/src/reference/index.md`                                          | Update                                  | Workflow, variable, task, permissions | F040 docs           |
| Navigation                 | `docs/src/SUMMARY.md`                                                  | Update if focused deployment page added | Register page                         | F040 docs           |
| Implemented Feature Record | `docs/src/features/040-github-validation-and-docs-deployment/index.md` | Create during close-out                 | Delivery evidence                     | lifecycle close-out |

## Validation Strategy

Render workflows, run actionlint/zizmor, test condition/permissions statically, mock gh API success/failure/idempotence,
and verify CI commands match mise tasks. Exercise Pages enablement manually in a disposable repository before delivery.

## Implementation Decomposition

1. Add validation workflow template.
2. Add gated Pages deployment workflow.
3. Add and test gh-based enable task.
4. Document permissions, recovery, and manual fallback.

## Dependencies and Parallelism

Depends on F010 and F020. Workflow templates and enable-task tests can proceed in parallel after task names stabilize.

## Rollout and Migration

Deployment remains disabled after template updates unless the repository variable is already set.

## Risks and Tradeoffs

GitHub API behavior and permissions may change. Keep calls narrow, inspect responses, and document manual recovery.

## Rejected Alternatives

- Disabled filename: GitHub cannot discover it as a workflow.
- Workflow dispatch only: does not provide automatic post-enable deployment.
- Source rewriting: creates avoidable dirty state and Copier conflicts.
- Deployment enabled by default: causes failures before Pages configuration.

## Open Questions

None.

## Deferred Decisions

Other CI and documentation hosting providers are future consumer-driven work.

## Planning Record

### Questions Asked and Answers

The user required validation, a disabled deployment workflow, and gh automation. They approved a repository-variable
gate and API-based Pages configuration.

### Assumptions

Generated projects target GitHub even when the remote is added after setup.

### Design Changes During Planning

The deployment workflow moved from optional generation to always-generated but disabled behavior.

### Source Material

AtomixOS and Conduit workflows; GitHub Pages and gh CLI contracts to verify during implementation.
