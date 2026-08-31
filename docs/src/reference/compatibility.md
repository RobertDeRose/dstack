# Compatibility and formula audits

dStack compatibility is read-oriented. Historical Beads are execution evidence, not a schema to migrate. Current
controllers accept supported historical feature roots/graphs when they can be resolved unambiguously; they do not
rewrite closed tasks, old labels, metadata aliases, or lifecycle topology merely to match today's formula.

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

## Automatic feature compatibility audit

When an approved active feature has a missing or stale `dstack.formula_version`, a normal lifecycle command creates or
reuses one native Bead labeled `dstack:work:formula-audit`. The controller adds ordinary Beads blockers from affected
open implementation tasks and closeout to that Bead, then stops. Native `bd ready` is the routing surface; no skill name,
resume command, or inter-agent payload is emitted.

The feature-review skill compares the accepted design and existing authorized work semantically against current
requirements. Different task names, grouping, review ceremony, or historical labels are not findings when the same
outcomes and validation are already covered.

- **No material delta:** run `feature audit-complete`; it closes the native audit Bead and stamps the current contract
  version on the feature root. No user approval is required.
- **Material delta:** present only the minimum design/task/dependency changes and rationale. Do not mutate approved work
  until the user approves reauthorization. The normal review/approval path records the current contract version, and the
  audit Bead remains the blocker until the review skill completes it.

The version stamp is the compatibility cache and the audit itself is ordinary Beads work; no separate audit state,
packet, migration map, or compatibility database exists.

## Legacy adoption

`/adopt-feature` remains an explicit compatibility boundary only for genuinely old active workflows that cannot execute
under the current lifecycle at all. It does not run on routine formula upgrades and is not used to clean historical
metadata. Retries derive identity from native Beads/Git evidence; no migration map is stored.
