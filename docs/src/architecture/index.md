# Workflow architecture

## Components

- `skills/` contains the installable workflows. Each skill owns its scripts and references.
- `skills/setup-project/template/` is the self-contained Copier scaffold installed with `/setup-project`.
- Root `copier.yml` exposes the same scaffold for repository development and integration tests.
- Beads stores live feature state and dependencies; `.beads/formulas/dstack-feature.formula.toml` defines the lifecycle
  graph.
- `docs/src/features/<slug>/design.md` owns intended feature behavior.
- Reader pages under `docs/src/` own supported current behavior.
- Implemented-feature `index.md` pages preserve delivery reconciliation and audit evidence.

## Authority boundaries

Skills CLI installs and updates workflow code. Copier records and applies scaffold evolution. Beads owns executable
work. Git commits and tests provide implementation evidence. No helper silently substitutes one authority for another.

## Template rendering boundary

New-project setup treats the structured project brief as the only source for initial product facts. Every project kind
receives the same minimal reader file set; kind changes only the future-concern guidance in documentation conventions.
The template omits architecture, usage, development-overview, and reference-overview pages until implementation creates
concrete content for them. Copier records the brief so later template renders remain deterministic.

## Safety invariants

- New-project setup does not overwrite or migrate existing project content.
- Remote template overrides require an explicit reviewed ref and never fall back silently to `HEAD`.
- Human feature commands use stable slugs or names; opaque Beads IDs remain mutation and audit details.
- Feature implementation cannot become ready before specification reconciliation.
- Reader documentation must stand alone rather than embedding internal designs or legacy task files.
- Delivery follows documentation reconciliation, validation, and independent drift/delivery reviews.

## Update flow

The installed setup skill renders its bundled template, then records the official repository and matching release tag in
`.copier-answers.yml`. `/update-project` discovers eligible published tags and lets Copier perform the three-way update.
`/migrate-workflow` handles repositories that predate the Copier/Beads contract.

## Generated tooling authority

Every generated project receives one universal `mise.toml` task/tool interface and one `hk.pkl` quality policy. The hk
binary and both versioned Pkl imports are pinned together; fuzzy versions for the other tools become deterministic in
the project-owned `mise.lock`. The generated provisioner ignores user-global mise configuration so that lock resolution
and locked installation cover only project-declared tools.

Copier only renders files. After rendering and optional Git initialization, `/setup-project` invokes the generated
`scripts/setup-tooling.py`. A conflict-free `/update-project` invokes that same project-local provisioner after Copier
reconciliation. An update with conflicts never executes newly rendered project code. Provisioning resolves the lock,
installs with `--locked`, then installs hk hooks as a separate stage so hook failure cannot erase successful
lock/install state.

Language quality profiles extends these same generated files from one canonical `language_profiles` answer. Recognized
profiles compose by direct membership-gated template sections; `other` is exclusive and preserves only the universal
baseline. Multiple profiles apply one root policy to a polyglot repository, not package-local or monorepo configuration.
Setup collects an explicit selection, while updates preserve it unless the user explicitly adds or removes profiles. The
existing provisioner and conflict gate remain the only network-backed tooling path. Source steps are file-gated; project
checks are root-manifest-gated. Profiles never create manifests, dependencies, source, package roots, or package-local
policy. The Nix exception keeps the universal four-platform lock while atomically removing only nixfmt-rs's unsupported
macOS x64 table before locked installation.

GitHub validation and docs deployment consumes the stable named tasks without adding package manifests, application
source, or duplicate CI policy. Generated projects include a documentation deployment workflow, but repository creation
and Copier updates never enable it. The workflow accepts only pushes to the configured default branch and explicit
manual dispatches; both build and deploy jobs require `DOCS_DEPLOYMENT_ENABLED` to equal `true`, so pull requests and
forks cannot deploy.

The build job receives only `contents: read`, installs the committed mise lock in isolation, runs the existing
`docs:build` task, and uploads `docs/book`. The deploy job alone receives `pages: write` and `id-token: write`, targets
the `github-pages` environment, and publishes the reviewed artifact. This separates untrusted change validation from the
credentialed deployment boundary.

Enablement is a separate administrative boundary: an operator supplies an external, authenticated GitHub CLI with
repository administration access. The helper configures Pages with `build_type=workflow` before setting the repository
variable. Deployment therefore requires both repository-side Pages configuration and an exact true variable; rendering
or updating the workflow alone grants nothing.
