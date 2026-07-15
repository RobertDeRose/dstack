# Planned features

This page is the human-readable roadmap. Beads is authoritative for live status, dependencies, claims, and ready-work
selection.

## Project direction

dstack will turn its current documentation-first workflow scaffold into a complete, reproducible project-development
baseline. New projects will begin with truthful project-kind-aware documentation, mise-managed tools, hk quality gates,
language-scoped checks, GitHub validation, opt-in Pages deployment, and later monorepo composition.

The sequence establishes the smallest shared contracts first. Purposeful documentation and universal tooling can be
reviewed independently. Language profiles extend the universal baseline. GitHub workflows depend on stable docs and task
names. Monorepo support follows only after single-package profile composition is proven.

## Roadmap conventions

- Feature numbers are stable and zero-padded: `010`, `020`, `030`.
- Directory names use `<num>-<slug>`.
- Detailed intent belongs in each feature's `design.md`.
- Each feature is one Beads epic/molecule; lifecycle and implementation work are tasks beneath it.
- Human workflow references use `<num>-<slug>`, `F<num>`, or the feature name. Root hashes are retained only for audit.
- Live execution state is queried through Beads.
- Completed features move into [Implemented features](features/index.md).
- Live lifecycle state is summarized as `design`, `spec-review`, `implementation`, `close-out`, `delivery-ready`,
  `delivered`, `deferred`, or `blocked`.

## Feature map

| Feature                                                                             | Beads root       | Roadmap state | Dependencies | Design                                                                 |
|-------------------------------------------------------------------------------------|------------------|---------------|--------------|------------------------------------------------------------------------|
| `010-purposeful-project-scaffold` — Purposeful project scaffold                     | `dstack-mol-ln9` | delivered     | —            | [Design](features/010-purposeful-project-scaffold/design.md)           |
| `020-universal-project-tooling` — Universal project tooling                         | `dstack-mol-lg3` | delivered     | —            | [Design](features/020-universal-project-tooling/design.md)             |
| `030-language-quality-profiles` — Language quality profiles                         | `dstack-mol-ni2` | delivered     | F020         | [Design](features/030-language-quality-profiles/design.md)             |
| `040-github-validation-and-docs-deployment` — GitHub validation and docs deployment | `dstack-mol-8fe` | delivered     | F010, F020   | [Design](features/040-github-validation-and-docs-deployment/design.md) |
| `050-monorepo-tooling-layout` — Monorepo tooling layout                             | `dstack-mol-7s4` | design        | F030         | [Design](features/050-monorepo-tooling-layout/design.md)               |

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
- Monorepo support is later work and must not complicate the first single-package delivery.

## Open project decisions

No planning-blocking cross-feature decisions remain. F050 intentionally retains an implementation-time research question
about current stable mise support for package-local configuration.

## Recommended next work

Start `050-monorepo-tooling-layout`; its lifecycle includes the planned mise capability research. F040's waived live
Pages exercise remains recorded with its GitHub API, permission, and provisioning risk.
