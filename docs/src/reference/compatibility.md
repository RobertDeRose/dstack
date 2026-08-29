# Compatibility and formula audits

dStack compatibility is read-oriented. Historical Beads are execution evidence, not a schema to migrate. Current
controllers accept supported historical feature roots/graphs when they can be resolved unambiguously; they do not
rewrite closed tasks, old labels, metadata aliases, or lifecycle topology merely to match today's formula.

## Supported runtime

- Python: 3.14 (package lock: 3.14.7)
- Beads: 1.2.2 exact supported build
- mdBook: 0.5.3

The launcher resolves these from the package lock; ambient `PATH` tools such as a Homebrew Beads build are outside the
tested controller boundary.

## Formula infrastructure

The package pins supported Python, Beads, mdBook, and formula source. Controller entry points verify the locked runtime
and use the two packaged dStack formulas as authority. Native pours expose the packaged formula only for the operation.
Legacy repositories that tracked old formula copies keep those historical bytes unchanged, and projects without a copy
are left without one afterward. Formula infrastructure therefore creates no persistent migration state.

Each formula carries a semantic contract version. The feature root records the version that created it and the latest
version whose semantics were approved/audited. A package release increments a formula contract version only when the
planning/review expectations materially change.

## Automatic feature compatibility audit

When an approved active feature has a missing or stale `dstack.formula_version`, a normal lifecycle command returns an
internal `audit_required` instruction naming the current review skill and the previous/current contract versions. The
core skill immediately performs that review; users do not invoke an audit mode.

The audit compares the accepted design and existing authorized work semantically against current requirements. Different
task names, grouping, review ceremony, or historical labels are not findings when the same outcomes and validation are
already covered.

- **No material delta:** run the controller's internal `feature audit-complete` transition, stamp the current contract
  version on the root/current work, and retry the original command. No user approval is required.
- **Material delta:** present only the minimum design/task/dependency changes and rationale. Do not mutate approved work
  until the user approves reauthorization. The normal review/approval path then records the current contract version.

The version stamp is the audit cache; no separate audit state, packet, migration map, or compatibility database exists.

## Legacy adoption

`/adopt-feature` remains an explicit compatibility boundary only for genuinely old active workflows that cannot execute
under the current lifecycle at all. It does not run on routine formula upgrades and is not used to clean historical
metadata. Retries derive identity from native Beads/Git evidence; no migration map is stored.
