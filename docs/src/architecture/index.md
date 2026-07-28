# Workflow architecture

## Components

- `skills/` contains the installable workflows. Each skill owns its scripts and references.
- `skills/setup-project/template/` is the canonical Copier scaffold used by both repository and skill entry points.
- Root `copier.yml` exposes the same scaffold for repository development and integration tests.
- Beads stores live feature state and dependencies; `.beads/formulas/dstack-feature.formula.toml` defines the lifecycle
  graph.
- `docs/src/features/<slug>/design.md` owns intended feature behavior.
- Reader pages under `docs/src/` own supported current behavior.
- Implemented-feature `index.md` pages preserve delivery reconciliation and audit evidence.

## Authority boundaries

Skills CLI installs and updates workflow code. Copier records and applies scaffold evolution. Beads owns executable
work. Git commits and tests provide implementation evidence. No helper silently substitutes one authority for another.

## Monorepo tooling ownership

Monorepo answers remain Copier-recorded state. Root `mise.toml`, `mise.lock`, hk policy, documentation, workflow state,
and the tooling provisioner remain repository authorities. Explicit package roots receive task-only mise configs; root
configuration owns the profile-tool union and aggregate check/fix dependencies. Setup and update render those
deterministic package configs from Copier answers without package discovery or a progress manifest.

Ordinary managed template changes retain Copier's three-way update behavior, and previously recorded package configs
refresh from current answers. If a newly requested package config path already contains a project file, update preserves
its bytes and writes the generated alternative under `migration/copier-adoption-candidates/<same-relative-path>`.
Candidate presence blocks generated tooling execution until explicit reconciliation.

## Template rendering boundary

New-project setup treats the structured project brief as the only source for initial product facts. Every project kind
receives the same minimal reader file set; kind changes only the future-concern guidance in documentation conventions.
The template omits architecture, usage, development-overview, and reference-overview pages until implementation creates
concrete content for them. Copier records the brief so later template renders remain deterministic.

## Validation policy

Root and generated hk configurations prefer version-pinned built-in steps. Native file locking coordinates independent
checks; explicit dependencies are reserved for demonstrated output ownership rather than global serialization.

## Migration boundary

Legacy adoption is additive. A committed session-authority record binds execution to the user-selected base SHA,
migration branch, exact worktree, and Git repository; its original introduction commit is immutable, so later branches,
manifests, and checkpoint commits cannot replace authority or authorize resume. Resume events are separate audit data.
The migration manifest records pre/post hook capabilities, artifact dispositions, contextual safety decisions,
feature-specific semantic evidence, and verified checkpoints; it does not replace Beads as live work authority or Copier
as scaffold authority. Project-owned files remain authoritative through candidate reconciliation. Only the rendered
project-local provisioner may install locked tools and hooks, and ordinary Git commits remain the checkpoint authority.

## Repository identity boundary

Migration distinguishes the active worktree path from canonical repository identity. Explicit recorded answers win;
otherwise the primary Git common directory supplies the project name and slug, and `refs/remotes/origin/HEAD` supplies
the default branch; only a primary worktree may use its current branch as evidence. A suffixed migration-worktree
basename is never adopted as project identity. Beads initialization is collaborative and non-stealth: expected control
files and the formula enter the workflow-owned branch commit, while the embedded database remains local Dolt storage.
Database path/name, project ID, repository root, and issue prefix must match before import or verification. Cross-clone
issue history uses a Dolt remote (`bd dolt push`/`bd bootstrap`), not committed database files or JSONL. Large imports
derive and reconcile the complete deterministic issue/status/parent/relationship set before trusting phase state and
rejects unexpected migrated records, then uses bounded Dolt batch commits per feature state and relationship phase. The
manifest remains a recovery cursor, never independent proof that records exist. Finalization is a journaled staging
transaction that seals archive digests and parsed task identity; finalized verification compares the exact recursive
archive and current feature/design/task inventory with that sealed record.

## Safety invariants

- New-project setup does not overwrite or migrate existing project content.
- Remote template overrides require an explicit reviewed ref and never fall back silently to `HEAD`.
- Human feature commands use stable slugs or names; opaque Beads IDs remain mutation and audit details.
- Feature implementation cannot become ready before specification reconciliation.
- Reader documentation must stand alone rather than embedding internal designs or legacy task files.
- Delivery follows documentation reconciliation, validation, and independent drift/delivery reviews.

## Update flow

Setup and update resolve either the newest stable tag or the explicitly selected unstable default-branch HEAD and
persist its SHA plus channel in `.copier-answers.yml`. Setup first verifies its installed bundle matches that exact
commit; update renders the selected source through Copier. `/update-project` preserves the channel and lets Copier
perform the three-way update. The dstack template source may explicitly bootstrap itself with `--adopt --unstable`;
`/migrate-workflow` handles other repositories that predate the Copier/Beads contract.

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
