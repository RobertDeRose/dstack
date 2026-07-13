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
