# Planned features

This page is the human-readable roadmap. Beads is authoritative for live status, dependencies, claims, and ready-work
selection.

## Project direction

dstack will turn its current documentation-first workflow scaffold into a complete, reproducible project-development
baseline. New projects begin with truthful project-kind-aware documentation, mise-managed tools, hk quality gates,
language-scoped checks, GitHub validation, and opt-in Pages deployment. The next work simplifies the generated hk
policy, then makes legacy migration additive, contextual, and hook-safe before monorepo composition extends that stable
base.

The sequence establishes the smallest shared contracts first. Purposeful documentation and universal tooling are
delivered. Language profiles and GitHub workflows extend that baseline. hk policy simplification restores native runner
behavior before both migration preservation and monorepo composition consume the generated policy. Migration safety and
clarity then protects existing project checks and verified history without blocking independent monorepo design review.

## Roadmap conventions

- Directory names use `<slug>`.
- Detailed intent belongs in each feature's `design.md`.
- Each feature is one Beads epic/molecule; lifecycle and implementation work are tasks beneath it.
- Human workflow references use `<slug>` or the feature name. Root hashes are retained only for audit.
- Live execution state is queried through Beads.
- Completed features move into [Implemented features](features/index.md).
- Live lifecycle state is summarized as `design`, `spec-review`, `implementation`, `close-out`, `delivery-ready`,
  `delivered`, `deferred`, or `blocked`.

## Feature map

| Feature                                                                         | Beads root       | Roadmap state | Dependencies                                           | Design                                                             |
|---------------------------------------------------------------------------------|------------------|---------------|--------------------------------------------------------|--------------------------------------------------------------------|
| `purposeful-project-scaffold` — Purposeful project scaffold                     | `dstack-mol-ln9` | delivered     | —                                                      | [Design](features/purposeful-project-scaffold/design.md)           |
| `universal-project-tooling` — Universal project tooling                         | `dstack-mol-lg3` | delivered     | —                                                      | [Design](features/universal-project-tooling/design.md)             |
| `language-quality-profiles` — Language quality profiles                         | `dstack-mol-ni2` | delivered     | Universal project tooling                              | [Design](features/language-quality-profiles/design.md)             |
| `github-validation-and-docs-deployment` — GitHub validation and docs deployment | `dstack-mol-8fe` | delivered     | Purposeful project scaffold, Universal project tooling | [Design](features/github-validation-and-docs-deployment/design.md) |
| `hk-policy-simplification` — hk policy simplification                           | `dstack-mol-5v0` | delivered     | Language quality profiles                              | [Design](features/hk-policy-simplification/design.md)              |
| `migration-safety-and-clarity` — Migration safety and clarity                   | `dstack-mol-tki` | design        | hk policy simplification                               | [Design](features/migration-safety-and-clarity/design.md)          |
| `monorepo-tooling-layout` — Monorepo tooling layout                             | `dstack-mol-7s4` | design        | Language quality profiles, hk policy simplification    | [Design](features/monorepo-tooling-layout/design.md)               |

## Cross-cutting decisions

- Every generated project receives the universal mise/hk/docs baseline.
- Tool aliases such as `latest`, `stable`, and `lts` reduce template maintenance; each new project commits the resolved
  `mise.lock` for determinism.
- Project kinds are library, CLI, service, application, infrastructure, documentation, and other.
- Setup requires purpose, intended users, current scope, and boundaries; pages without concrete content are omitted.
- Initial language profiles are Python, TypeScript, Rust, Go, Elixir, Nix, and other. TypeScript uses Aube. Profiles do
  not generate application manifests or source; the Nix profile intentionally excludes macOS x64.
- GitHub validation is generated universally. Pages deployment is committed but gated by `DOCS_DEPLOYMENT_ENABLED`; an
  explicit gh-backed mise task enables it.
- hk uses built-ins, native config discovery, and file locking by default; custom steps and dependencies require a
  concrete behavioral reason.
- Legacy migration preserves existing hk steps unless the user explicitly approves removal, commits durable task
  archives, asks contextual questions, and never uses `--no-verify`.
- Monorepo support follows hk policy simplification and must not complicate the single-package contract.

## Open project decisions

No planning-blocking cross-feature decisions remain. Monorepo tooling layout intentionally retains an
implementation-time fact-finding task about current stable mise support for package-local configuration; every supported
result must preserve the already-decided root/package ownership contract.

## Recommended next work

Implement `migration-safety-and-clarity` or `monorepo-tooling-layout` from the delivered simplified policy. GitHub
validation and docs deployment's waived live Pages exercise remains recorded with its GitHub API, permission, and
provisioning risk.
