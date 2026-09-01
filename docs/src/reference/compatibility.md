# Compatibility and formula audits

dStack compatibility is read-oriented. Historical Beads are execution evidence, not a schema to migrate. Current
controllers operate on current molecules and do not rewrite closed tasks, old labels, metadata aliases, or lifecycle
topology merely to match today's formula.

## Supported runtime

- Python: 3.14 (`uv tool install` enforces `pyproject.toml`)
- Beads: 1.2.2 exact supported build on `PATH`
- mdBook: 0.5.3 on `PATH` when documentation validation is required

The installed `dstack` executable is the controller boundary. It validates the Beads build before Beads-backed work and
reports missing external executables directly; there is no package-relative launcher.

## Formula infrastructure

The Python package carries the two dStack formulas as authority. Controller entry points validate required external
tools and use the packaged formula source directly. Native pours expose the packaged formula only for the operation.
Legacy repositories that tracked old formula copies keep those historical bytes unchanged, and projects without a copy
are left without one afterward. Formula infrastructure therefore creates no persistent migration state.

Each formula carries a semantic contract version. The feature root records the version that created it and the latest
version whose semantics were approved/audited. A package release increments a formula contract version only when the
planning/review expectations materially change.

## Feature compatibility audit

An approved active feature continues to execute according to native Beads readiness even when its
`dstack.formula_version` is missing or older than the packaged contract. Formula versions are review compatibility
metadata, not an execution gate. When that feature is explicitly reviewed under the current contract, the existing
molecule, implementation work, dependencies, labels, and statuses remain exactly as they were approved. Formula drift is
a compatibility question over that native intent, not new workflow work.

The feature-review skill compares the accepted design and existing authorized work semantically against current
requirements. Different task names, grouping, review ceremony, or historical labels are not findings when the same
outcomes and validation are already covered.

- **No material delta:** run `feature audit-complete`; it stamps the current contract version on the feature root and
  changes no Bead topology or lifecycle status. No user approval is required.
- **Material delta:** present only the minimum design/task/dependency changes and rationale. Do not mutate approved work
  until the user approves reauthorization. Reuse the existing specification, human gate, and approval milestone; the
  normal review/approval path records the current contract version after the approved delta converges.

The root version stamp is only a compatibility cache. There is no audit Bead, fifth lifecycle role, dependency rewrite,
packet, migration map, or compatibility database.

## Historical topology

Active historical graphs that do not contain the current dStack molecule are left untouched. dStack has no setup,
adoption, or topology-migration command. Such work remains directly manageable through native Beads; moving it into a
new current feature is an explicit user planning decision, not an automatic compatibility operation.
