# Workflow architecture

## Components

- `skills/` contains the installable workflows. Each skill owns its scripts and references.
- `skills/setup-project/template/` is the self-contained Copier scaffold installed with `/setup-project`.
- Root `copier.yml` exposes the same scaffold for repository development and integration tests.
- Beads stores live feature state and dependencies; `.beads/formulas/feature-lifecycle.formula.toml` defines the
  lifecycle graph.
- `docs/src/features/<num>-<slug>/design.md` owns intended feature behavior.
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
- Human feature commands use stable number/slug or names; opaque Beads IDs remain mutation and audit details.
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

F030 may extend the shared mise/hk files with language profiles. F040 consumes the named tasks for GitHub validation.
Generated projects do not receive dstack's release task or repository-specific language, CI, shell, YAML, or security
checks from this baseline.
